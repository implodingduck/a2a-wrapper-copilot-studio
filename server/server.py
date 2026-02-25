import json
import logging
import os
import jwt
import requests
import uvicorn

from cryptography.hazmat.primitives import serialization
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    APIKeySecurityScheme,
    AuthorizationCodeOAuthFlow,
    OAuth2SecurityScheme,
    OAuthFlows
)
from .agent_executor import (
    CopilotStudioAgentExecutor,  # type: ignore[import-untyped]
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

tenant_id = os.getenv('COPILOTSTUDIOAGENT__TENANTID')
client_id = os.getenv('COPILOTSTUDIOAGENT__AGENTAPPID')

class OAuthMiddleware(BaseHTTPMiddleware):
    """Middleware to check for OAuth token authentication."""

    def __init__(self, app):
        super().__init__(app)
        self.jwt_keys = {}
        response = requests.get(f"https://login.microsoftonline.com/{tenant_id}/discovery/keys")
        
        
        keys = response.json()['keys']
        for k in keys:
            #print(k)
            rsa_pem_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(k))
            rsa_pem_key_bytes = rsa_pem_key.public_bytes(
            encoding=serialization.Encoding.PEM, 
            format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            #print(rsa_pem_key_bytes)
            self.jwt_keys[k['kid']] = rsa_pem_key_bytes
            #print("-------------")
        
    async def dispatch(self, request: Request, call_next):

        if (request.url.path == "/.well-known/agent-card.json" and request.method == "GET"):
            return await call_next(request)
        

        # Check for Authorization header
        auth_header = request.headers.get("Authorization")

        # set a response header for  WWW-Authenticate with the appropriate challengeHTTP 401; Unauthorized

        response_headers = {
            "WWW-Authenticate": f'Bearer realm="", authorization_uri="https://login.microsoftonline.com/{tenant_id}/oauth2/authorize", client_id="{client_id}"'
        }
        
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "message": "Bearer token is required in the Authorization header"},
                headers=response_headers
            )
        
        token = auth_header.split(" ")[1]
        auth_header = request.headers.get('Authorization')
        try:
            token = auth_header.split(' ')[1]
            print(token)
            #print(settings.CLIENT_ID)
            alg = jwt.get_unverified_header(token)['alg']
            kid = jwt.get_unverified_header(token)['kid']
            claims = jwt.decode(token,key=self.jwt_keys[kid], algorithms=[alg], audience=[client_id])
            print(claims)
        except Exception as e:
            return JSONResponse(status_code=401, content={"message": f"Error: {e}"}, headers=response_headers)
        
        # Here you would implement your token validation logic
        # For example, you could validate the token with Azure AD or another identity provider
        
        # If token is invalid:
        # return JSONResponse(
        #     status_code=403,
        #     content={"error": "Forbidden", "message": "Invalid or expired token"}
        # )
        
        return await call_next(request)

class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Middleware to check for API key authentication."""
    
    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key
    
    async def dispatch(self, request: Request, call_next):
        # Allow access to the agent card endpoints without authentication
        if (request.url.path == "/.well-known/agent-card.json" and request.method == "GET"):
            return await call_next(request)
        
        # Check for X-API-Key header
        provided_key = request.headers.get("X-API-Key")
        
        if not provided_key:
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "message": "X-API-Key header is required"}
            )
        
        if provided_key != self.api_key:
            return JSONResponse(
                status_code=403,
                content={"error": "Forbidden", "message": "Invalid API key"}
            )
        
        return await call_next(request)


port = int(os.getenv('PORT', 8000))
url = f"https://{os.getenv('CONTAINER_APP_HOSTNAME')}/" if os.getenv('CONTAINER_APP_HOSTNAME') else f'http://localhost:{port}/'
api_key = os.getenv('API_KEY', '')

if __name__ == '__main__':
    # --8<-- [start:AgentSkill]
    skill = AgentSkill(
        id='CopilotStudioInvokeSkill',
        name='Invoke Skill',
        description='Invokes a copilot studio agent',
        tags=['echo', 'test'],
        examples=['hi', 'hello world'],
    )

    # --8<-- [start:AgentCard]
    # This will be the public-facing agent card
    public_agent_card = AgentCard(
        name='Copilot Studio Agent',
        description='An agent that invokes Copilot Studio capabilities',
        url=f'{url}',
        version='1.0.0',
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],  # Only the basic skill for the public card
        security=[{ "entra": [] }],
        security_schemes={
            "entra": OAuth2SecurityScheme(
                type="oauth2",
                flows=OAuthFlows(
                    authorizationCode=AuthorizationCodeOAuthFlow(
                        authorizationUrl=f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize",
                        tokenUrl=f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
                        scopes={
                            f"api://{client_id}/invoke": "Access to invoke the Copilot Studio Agent"
                        }
                    )
                )
            )
        }
    )

    request_handler = DefaultRequestHandler(
        agent_executor=CopilotStudioAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=public_agent_card,
        http_handler=request_handler,
    )
    
    # Build the app and add authentication middleware
    app = server.build()
    
    # Add API key authentication middleware if API_KEY is configured
    if os.getenv('COPILOTSTUDIOAGENT__CLIENTSECRET'):
        # If the environment variables for Copilot Studio Agent are set, we assume authentication is handled via tokens and skip API key middleware
        logger.info("Copilot Studio Agent credentials detected. Skipping API key middleware.")
        app.add_middleware(OAuthMiddleware)  # You would implement OAuthMiddleware to handle token-based authentication

    elif api_key:
        app.add_middleware(APIKeyAuthMiddleware, api_key=api_key)

    else:
        print("Warning: API_KEY not set. Authentication is disabled.")

    uvicorn.run(app, host='0.0.0.0', port=port)
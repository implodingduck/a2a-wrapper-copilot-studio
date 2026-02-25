from ast import List
import logging

import os
from typing import List
import random
from uuid import uuid4

import httpx

import uvicorn

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.client.errors import A2AClientHTTPError
from a2a.types import (
    AgentCard,
    Message,
)
from a2a.utils.constants import (
    AGENT_CARD_WELL_KNOWN_PATH,
    EXTENDED_AGENT_CARD_PATH,
)
from dotenv import load_dotenv
from msal import PublicClientApplication

load_dotenv()

tenant_id = os.getenv('COPILOTSTUDIOAGENT__TENANTID')
client_id = os.getenv('COPILOTSTUDIOAGENT__AGENTAPPID')

authority = f"https://login.microsoftonline.com/{tenant_id}"
scopes = [f"api://{client_id}/invoke"]


app: PublicClientApplication = PublicClientApplication(client_id, authority=authority)

# Function with type hints for return value and parameters
def acquire_token(app: PublicClientApplication, scopes: List[str]):
    accounts = app.get_accounts()
    if accounts:
        return app.acquire_token_silent(scopes, account=accounts[0])
    return app.acquire_token_interactive(scopes=scopes)


async def call_a2a(query: str, httpx_client: httpx.AsyncClient, agent_card: AgentCard):
    
    # Acquire token
    token_response = acquire_token(app, scopes)
    if token_response and "access_token" in token_response:
        print("Access Token:", token_response["access_token"])
        access_token = token_response["access_token"]

    httpx_client.headers.update({'Authorization': f'Bearer {access_token}'})
    httpx_client.headers.update({'X-API-Key': os.getenv('API_KEY', 'your-secret-api-key-here')})
    config = ClientConfig(httpx_client=httpx_client)
    factory = ClientFactory(config)
    client = factory.create(agent_card)

    message = Message(
        role='user',
        parts=[{'kind': 'text', 'text': query}],
        message_id=uuid4().hex,
    )

    try:
        async for response in client.send_message(message):
            print(response)
    except A2AClientHTTPError as e:
        print(f"Error during send_message: {e.status_code} - {e.message}")


async def main() -> None:
    # Configure logging to show INFO level messages
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)  # Get a logger instance

    # --8<-- [start:A2ACardResolver]

    base_url = os.getenv('BASE_URL', 'http://localhost:8000')

    async with httpx.AsyncClient(timeout=60) as httpx_client:
        # Initialize A2ACardResolver
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=base_url,
            # agent_card_path uses default, extended_agent_card_path also uses default
        )
        # --8<-- [end:A2ACardResolver]

        # Fetch Public Agent Card and Initialize Client
        final_agent_card_to_use: AgentCard | None = None

        try:
            logger.info(
                f'Attempting to fetch public agent card from: {base_url}{AGENT_CARD_WELL_KNOWN_PATH}'
            )
            _public_card = (
                await resolver.get_agent_card()
            )  # Fetches from default public path
            logger.info('Successfully fetched public agent card:')
            logger.info(
                _public_card.model_dump_json(indent=2, exclude_none=True)
            )
            final_agent_card_to_use = _public_card
            logger.info(
                '\nUsing PUBLIC agent card for client initialization (default).'
            )

            if _public_card.supports_authenticated_extended_card:
                try:
                    logger.info(
                        f'\nPublic card supports authenticated extended card. Attempting to fetch from: {base_url}{EXTENDED_AGENT_CARD_PATH}'
                    )
                    auth_headers_dict = {
                        'Authorization': 'Bearer dummy-token-for-extended-card'
                    }
                    _extended_card = await resolver.get_agent_card(
                        relative_card_path=EXTENDED_AGENT_CARD_PATH,
                        http_kwargs={'headers': auth_headers_dict},
                    )
                    logger.info(
                        'Successfully fetched authenticated extended agent card:'
                    )
                    logger.info(
                        _extended_card.model_dump_json(
                            indent=2, exclude_none=True
                        )
                    )
                    final_agent_card_to_use = (
                        _extended_card  # Update to use the extended card
                    )
                    logger.info(
                        '\nUsing AUTHENTICATED EXTENDED agent card for client initialization.'
                    )
                except Exception as e_extended:
                    logger.warning(
                        f'Failed to fetch extended agent card: {e_extended}. Will proceed with public card.',
                        exc_info=True,
                    )
            elif (
                _public_card
            ):  # supports_authenticated_extended_card is False or None
                logger.info(
                    '\nPublic card does not indicate support for an extended card. Using public card.'
                )

        except Exception as e:
            logger.error(
                f'Critical error fetching public agent card: {e}', exc_info=True
            )
            raise RuntimeError(
                'Failed to fetch the public agent card. Cannot continue.'
            ) from e

        await call_a2a(
            query='How can I create an Azure Container app?',
            httpx_client=httpx_client,
            agent_card=final_agent_card_to_use,
        )

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
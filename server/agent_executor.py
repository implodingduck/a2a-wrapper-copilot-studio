import logging
import msal
import os

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    AgentCard,
    FilePart,
    FileWithBytes,
    FileWithUri,
    Part,
    TaskState,
    TextPart,
)
from a2a.utils import new_agent_text_message, get_message_text
from microsoft_agents.activity import ActivityTypes, load_configuration_from_env
from microsoft_agents.copilotstudio.client import (
    ConnectionSettings,
    CopilotClient,
)
import uuid

logger = logging.getLogger(__name__)

class GenericThread():
    def __init__(self):
        self.id = uuid.uuid4()
        self.messages = [] # list of strings

class CopilotStudioAgent:
    """Copilot Studio Agent."""

    def __init__(self, access_token: str):
        self.threads = {}
        self.access_token = access_token

    async def create_thread(self):
        thread = GenericThread()
        self.threads[thread.id] = thread
        return thread

    async def run_conversation(self, thread_id: str, user_message: str) -> list[str]:
        # For demo purposes, just echo the message back with a prefix
        response = await self.invoke(user_message, self.access_token)
        logging.info(f'Agent received message: {user_message} in thread {thread_id}')
        logging.info(f'Agent responding with: {response} in thread {thread_id}')
        self.threads[thread_id].messages.append(user_message)
        self.threads[thread_id].messages.append(response)
        return self.threads[thread_id].messages

    async def create_client(self, access_token):
        settings = ConnectionSettings(
            environment_id=os.environ.get("COPILOTSTUDIOAGENT__ENVIRONMENTID"),
            agent_identifier=os.environ.get("COPILOTSTUDIOAGENT__SCHEMANAME"),
            cloud=None,
            copilot_agent_type=None,
            custom_power_platform_cloud=None,
        )
        logger.info(f"Configuring settings...")
        logger.info(f"Got MCP ...")
        confidentialcredential = msal.ConfidentialClientApplication(
            os.environ.get("COPILOTSTUDIOAGENT__AGENTAPPID"),
            authority=f"https://login.microsoftonline.com/{os.environ.get('COPILOTSTUDIOAGENT__TENANTID')}",
            client_credential=os.environ.get("COPILOTSTUDIOAGENT__CLIENTSECRET")
        )
        logger.info(f"Acquiring Copilot Studio token on behalf of MCP token...")
        copilottoken = confidentialcredential.acquire_token_on_behalf_of(
            user_assertion=access_token,
            scopes=["https://api.powerplatform.com/.default"]
        )
        logger.info(f"Acquired Copilot Studio token: {copilottoken}")

        copilot_client = CopilotClient(settings, copilottoken["access_token"])
        return copilot_client
    
    async def invoke(self, text: str, access_token: str) -> str:
        print(f'CopilotStudioAgent received input: {text}')
        copilot_client =await self.create_client(access_token)
        act = copilot_client.start_conversation(True)
        logger.info("Starting conversation...")
        async for action in act:
            if action.text:
                logger.info(action.text)
                conversation_id = action.conversation.id
        logger.info(f"Conversation ID: {conversation_id}")
        replies = copilot_client.ask_question(text, conversation_id)
        async for reply in replies:
            if reply.type == ActivityTypes.message:
                logger.info(f"Received reply: {reply.text}")
                return reply.text

        #return f'Copilot Studio: {text}'


class GenericAgentExecutor(AgentExecutor):
    """An AgentExecutor that runs Azure AI Foundry-based agents.
    Adapted from the ADK agent executor pattern.
    """

    def __init__(self, card: AgentCard):
        self._card = card
        self._agent: CopilotStudioAgent | None = None
        self._active_threads: dict[
            str, str
        ] = {}  # context_id -> thread_id mapping

    async def _get_or_create_agent(self, access_token: str) -> CopilotStudioAgent:
        """Get or create the Copilot Studio agent."""
        if not self._agent:
            self._agent = CopilotStudioAgent(access_token)
        return self._agent

    async def _get_or_create_thread(self, context_id: str, access_token: str) -> str:
        """Get or create a thread for the given context."""
        if context_id not in self._active_threads:
            agent = await self._get_or_create_agent(access_token)
            thread = await agent.create_thread()
            self._active_threads[context_id] = thread.id
            logger.info(
                f'Created new thread {thread.id} for context {context_id}'
            )

        return self._active_threads[context_id]

    async def _process_request(
        self,
        message_parts: list[Part],
        context_id: str,
        task_updater: TaskUpdater,
        access_token: str
    ) -> None:
        """Process a user request through the Foundry agent."""
        try:
            # Convert A2A parts to text message
            user_message = self._convert_parts_to_text(message_parts)

            # Get agent and thread
            agent = await self._get_or_create_agent(access_token)
            thread_id = await self._get_or_create_thread(context_id, access_token)

            # Update status
            await task_updater.update_status(
                TaskState.working,
                message=new_agent_text_message(
                    'Processing your request...', context_id=context_id
                ),
            )

            # Run the conversation
            responses = await agent.run_conversation(thread_id, user_message)

            # Send responses back
            for response in responses:
                await task_updater.update_status(
                    TaskState.working,
                    message=new_agent_text_message(
                        response, context_id=context_id
                    ),
                )

            # Mark as complete
            final_message = responses[-1] if responses else 'Task completed.'
            await task_updater.complete(
                message=new_agent_text_message(
                    final_message, context_id=context_id
                )
            )

        except Exception as e:
            logger.error(f'Error processing request: {e}', exc_info=True)
            await task_updater.failed(
                message=new_agent_text_message(
                    f'Error: {e!s}', context_id=context_id
                )
            )

    def _convert_parts_to_text(self, parts: list[Part]) -> str:
        """Convert A2A message parts to a text string."""
        text_parts = []

        for part in parts:
            part = part.root
            if isinstance(part, TextPart):
                text_parts.append(part.text)
            elif isinstance(part, FilePart):
                # For demo purposes, just indicate file presence
                if isinstance(part.file, FileWithUri):
                    text_parts.append(f'[File: {part.file.uri}]')
                elif isinstance(part.file, FileWithBytes):
                    text_parts.append(f'[File: {len(part.file.bytes)} bytes]')
            else:
                logger.warning(f'Unsupported part type: {type(part)}')

        return ' '.join(text_parts)

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ):
        """Execute the agent request."""
        logger.info(f'Executing request for context: {context.context_id}')

        access_token = None

        if hasattr(context, 'call_context'):
            logger.info(f"Context has call_context attribute.")
            if hasattr(context.call_context, 'state'):
                logger.info(f"Context has call_context.state attribute.")
                logger.info(f"Call context state: {context.call_context.state}")
                headers = context.call_context.state.get("headers", {})
                logger.info(f"Extracted headers from call context state: {headers}")
                auth_header = headers.get("authorization", "")
                if auth_header.startswith("Bearer "):
                    access_token = auth_header.split(" ")[1]
                    logger.info(f"Extracted access token from Authorization header.")

        # Create task updater
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        # Notify task submission
        if not context.current_task:
            await updater.submit()

        # Start working
        await updater.start_work()

        # Process the request
        await self._process_request(
            context.message.parts,
            context.context_id,
            updater,
            access_token
        )

        logger.debug(
            f'Foundry agent execution completed for {context.context_id}'
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        """Cancel the ongoing execution."""
        logger.info(f'Cancelling execution for context: {context.context_id}')

        # For now, just log cancellation
        # In a full implementation, you might want to:
        # 1. Cancel any ongoing API calls
        # 2. Clean up resources
        # 3. Notify the task store

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.failed(
            message=new_agent_text_message(
                'Task cancelled by user', context_id=context.context_id
            )
        )

    async def cleanup(self):
        """Clean up resources."""
        if self._foundry_agent:
            await self._foundry_agent.cleanup_agent()
            self._foundry_agent = None
        self._active_threads.clear()
        logger.info('Foundry agent executor cleaned up')


def create_generic_agent_executor(card: AgentCard) -> GenericAgentExecutor:
    """Factory function to create a generic agent executor."""
    return GenericAgentExecutor(card)

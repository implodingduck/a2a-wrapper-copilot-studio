from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message, get_message_text


class EchoAgent:
    """Echo Agent."""

    async def invoke(self, text: str) -> str:
        print(f'EchoAgent received input: {text}')
        return f'Echo: {text}'


class EchoAgentExecutor(AgentExecutor):
    """Test AgentProxy Implementation."""

    def __init__(self):
        self.agent = EchoAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        raw_text = get_message_text(context.message) if context.message else ''
        result = await self.agent.invoke(raw_text)
        await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise Exception('cancel not supported')

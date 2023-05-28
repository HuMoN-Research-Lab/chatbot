import logging
import os
import uuid
from datetime import datetime
from typing import List

import discord
from pydantic import BaseModel

from chatbot.bots.assistants.course_assistant.course_assistant import CourseAssistant
from chatbot.bots.workers.student_profile_builder.student_profile_builder import StudentProfileBuilder
from chatbot.mongo_database.mongo_database_manager import MongoDatabaseManager
from chatbot.system.environment_variables import get_admin_users

TIME_PASSED_MESSAGE = """
> Some time passed and your memory of this conversation reset needed to be reloaded from the thread, but we're good now!
> 
> Provide the human with a brief summary of what you remember about them and this conversation so far.
"""

logger = logging.getLogger(__name__)


class Chat(BaseModel):
    title: str
    thread: discord.Thread
    assistant: CourseAssistant

    started_at: str = datetime.now().isoformat()
    chat_id: str = uuid.uuid4()
    messages: List = []

    class Config:
        arbitrary_types_allowed = True


def get_assistant(assistant_type: str, **kwargs):
    if assistant_type == "introduction":
        return StudentProfileBuilder(**kwargs)

    return CourseAssistant(**kwargs)


class ChatCog(discord.Cog):
    def __init__(self,
                 bot: discord.Bot,
                 mongo_database: MongoDatabaseManager):
        self._discord_bot = bot
        self._mongo_database = mongo_database
        self._active_threads = {}
        self._allowed_channels = os.getenv("ALLOWED_CHANNELS").split(",")
        self._allowed_channels = [int(channel) for channel in self._allowed_channels]
        self._course_assistant_llm_chains = {}

    @discord.slash_command(name="chat", description="Chat with the bot")
    @discord.option(name="initial_message",
                    description="The initial message to send to the bot",
                    input_type=str,
                    required=False)
    async def chat(self,
                   ctx: discord.ApplicationContext,
                   initial_text_input: str = None):

        if not ctx.channel.id in self._allowed_channels:
            logger.info(f"Channel {ctx.channel.id} is not allowed to start a chat")
            return

        chat_title = self._create_chat_title_string(str(ctx.user))
        logger.info(f"Starting chat {chat_title}")

        title_card_embed = await self._make_title_card_embed(str(ctx.user), chat_title)
        message = await ctx.send(embed=title_card_embed)

        await self._spawn_thread(message=message,
                                 initial_text_input=initial_text_input)

    @discord.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        try:
            # Make sure we won't be replying to ourselves.
            if payload.user_id == self._discord_bot.user.id:
                return

            # Make sure we're only responding to the correct emoji
            if not payload.emoji.name == '🧠':
                return

            # Make sure we're only responding to the admin users
            if not payload.user_id in get_admin_users():
                logger.info(f"User {payload.user_id} is not an admin user")
                return

            # Get the channel and message using the payload
            channel = self._discord_bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)

            await self._spawn_thread(message=message,
                                     initial_text_input=message.content
                                     )

        except Exception as e:
            print(f'Error: {e}')

    @discord.Cog.listener()
    async def on_message(self, message: discord.Message):
        logger.info(f"Received message: {message.content}")

        # Make sure we won't be replying to ourselves.
        if message.author.id == self._discord_bot.user.id:
            return

        # Only respond to messages in threads
        if not message.channel.__class__ == discord.Thread:
            return
        thread = message.channel
        # Only respond to messages in threads owned by the bot
        if not thread.owner_id == self._discord_bot.user.id:
            return

        # ignore if first character is ~
        if message.content[0] == "~":
            return
        try:
            chat = self._active_threads[thread.id]
        except KeyError:
            chat = await self._create_chat(thread=thread,
                                           title=self._create_chat_title_string(str(message.author)))

        logger.info(f"Sending message to the agent: {message.content}")

        await self._async_send_message_to_bot(chat=chat, input_text=message.content)

    async def _async_send_message_to_bot(self, chat: Chat, input_text: str):
        response_message = await chat.thread.send("`Awaiting bot response...`")
        try:

            async with response_message.channel.typing():
                bot_response = await chat.assistant.async_process_input(input_text=input_text)

            await response_message.edit(content=bot_response)

        except Exception as e:
            logger.error(e)
            await response_message.edit(content=f"Oh no, something went wrong! \nHere is the error:\n ```\n{e}\n```")

    def _create_chat_title_string(self, user_name: str) -> str:
        return f"{user_name}'s chat with {self._discord_bot.user.name}"

    async def _spawn_thread(self,
                            message: discord.Message,
                            initial_text_input: str = None,
                            ):
        user_name = str(message.author)
        chat_title = self._create_chat_title_string(user_name=user_name)
        thread = await message.create_thread(name=chat_title)

        chat = await self._create_chat(thread=thread,
                                       title=chat_title, )

        if initial_text_input is None:
            initial_text_input = f"A human has requested a chat!"
            await chat.thread.send(
                embed=self._initial_message_embed(message=message, initial_message=initial_text_input))

        await self._async_send_message_to_bot(chat=chat, input_text=initial_text_input)

    async def _create_chat(self,
                           thread: discord.Thread,
                           title: str,) -> Chat:

        if thread.id in self._active_threads:
            logger.warning(f"Thread {thread.id} already exists! Returning existing chat")
            return self._active_threads[thread.id]

        assistant = CourseAssistant()

        if thread.message_count > 0:
            message = await thread.send(
                f"Reloading memory from thread (might take a while if this was a long conversation)...")
            await assistant.load_memory_from_thread(thread=thread,
                                                    bot_name=str(self._discord_bot.user))

            prefix = f"> Memory reloaded from thread - Here's what we told the bot: ```{TIME_PASSED_MESSAGE}```> ...and it replied:"
            await message.edit(content=f"{prefix}\n\n...")
            bot_response = await assistant.async_process_input(input_text=TIME_PASSED_MESSAGE)
            reply = f"{prefix}\n\n{bot_response}"
            await message.edit(content=reply)


        chat = Chat(
            title=title,
            thread=thread,
            assistant=assistant
        )

        self._active_threads[thread.id] = chat
        return chat

    async def _make_title_card_embed(self, user_name: str, chat_title: str):
        return discord.Embed(
            title=chat_title,
            description=f"A conversation between {user_name} and the bot, started on {datetime.now()}",
            color=0x25d790,
        )

    def _initial_message_embed(self, message, initial_message):
        thread_intro = f"""
                   Remember! The bot...                   
                   ...ignores messages starting with ~                                
                   ...makes things up some times                    
                   ...cannot search the internet 
                   ...is doing its best 🤖❤️  
                   
                   Source code: 
                   https://github.com/jonmatthis/chatbot
                   This bot's prompt: 
                   https://github.com/jonmatthis/chatbot/blob/main/chatbot/assistants/course_assistant/course_assistant_prompt.py
                   
                   ------------------
                   ------------------
                   Beginning chat with initial message: 
                   
                   > {initial_message}
                    
                   """
        return discord.Embed(
            description=thread_intro,
            color=0x25d790,
        )

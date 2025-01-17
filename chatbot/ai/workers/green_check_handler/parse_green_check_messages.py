import logging
import os
import random
from pathlib import Path
from typing import Union

from dotenv import load_dotenv

from langchain import PromptTemplate, OpenAI
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from chatbot.ai.workers.green_check_handler.grab_green_check_messages import grab_green_check_messages
from chatbot.mongo_database.mongo_database_manager import MongoDatabaseManager
from chatbot.student_info.find_student_name import get_initials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PaperSummary(BaseModel):
    title: str = Field("", description="The title of the research article")
    author_year: str = Field("", description="The author and year of the research article (e.g. 'Smith et al. 2020')")
    citation: str = Field("", description="The citation to the research article")
    abstract: str = Field("", description="A copy-paste of the abstract of the research article")
    detailed_summary: str = Field("", description="A detailed summary/overview of the major points of the paper in a bulleted outline format")
    short_summary: str = Field("", description="A short (2-3 sentence) summary of the paper")
    very_short_summary: str = Field("", description="A very short one sentence summary of the research article")
    extremely_short_summary: str = Field("", description="An extremely short 6-10 word summary of the research article")
    basic_methodology: str = Field("", description="A basic description of the methodology used in the research article")
    tags: str = Field("", description="A list of tags formatted using #kebab-case-lowercase")
    summary_title: str = Field("", description="A summary title made by combining the `author_year` field with the `extremely_short_summary` field, like this: ['author_year'] - ['extremely_short_summary']")


    def __str__(self):
        tags = "\n".join(self.tags.split(" "))
        return f"""
# {self.summary_title}\n
## Title\n
{self.title}\n\n
## Citation:\n
{self.citation}\n\n
## Abstract\n
{self.abstract}\n\n
## Basic Methodology\n
{self.basic_methodology}\n\n
## Detailed Summary\n
{self.detailed_summary}\n\n
## Short Summary\n
{self.short_summary}\n\n
## Very Short Summary\n
{self.very_short_summary}\n\n
## Extremely Short Summary\n
{self.extremely_short_summary}\n\n
## Tags\n
{tags}
"""

class GreenCheckMessageParser:
    def __init__(self):
        load_dotenv()
        self._llm = OpenAI(model_name="text-davinci-003",
                           temperature=0,
                            max_tokens=-1,
                           streaming=True,
                           callbacks=[StreamingStdOutCallbackHandler()],
                           )

        self._parser = PydanticOutputParser(pydantic_object=PaperSummary)

        self._prompt_template = PromptTemplate(
            template="Use these instructions to convert the input text into a paper summary:\n "
                     "{format_instructions} \n\n"
                     "Input text: \n"
                     "___\n"
                     "{input_text}\n\n"
                     "___\n"
                     "DO NOT MAKE ANYTHING UP. ONLY USE TEXT FROM THE INPUT TEXT. \n"
                     "IF YOU DO NOT HAVE ENOUGH INFORMATION TO FILL OUT A FIELD SAY 'COULD NOT FIND IN INPUT TEXT'",

            input_variables=["input_text"],
            partial_variables={"format_instructions": self._parser.get_format_instructions()}
        )

    def parse_input(self, input_text: str) -> PaperSummary:
        _input_text = self._prompt_template.format_prompt(input_text=input_text)
        _output = self._llm(_input_text.to_string())
        response = self._parser.parse(_output)
        return response

    async def aparse_input(self, input_text: str) -> PaperSummary:
        response = self.parse_input(input_text=input_text)
        return response

async def parse_green_check_messages(overwrite: bool = False,
                                     save_to_json: bool = True,
                                     collection_name: str = "green_check_messages"):

    parser = GreenCheckMessageParser()

    mongo_database = MongoDatabaseManager()

    collection = mongo_database.get_collection(collection_name)
    all_entries = await collection.find().to_list(length=None)
    random.shuffle(all_entries)
    logger.info("Parsing green check messages")

    for entry in all_entries:

        print("=====================================================================================================")
        print(f"Green Check Messages for student: {entry['_student_name']}\n")
        print("=====================================================================================================")

        messages = entry["green_check_messages"]
        if len(messages) == 0:
            raise ValueError(f"Student {entry['_student_name']} has no green check messages")


        messages = "\n".join(messages)
        parsed_output = await parser.aparse_input(input_text=messages)


        await mongo_database.upsert(
            collection=collection_name,
            query={"_student_name": entry["_student_name"]},
            data={"$set": {"parsed_output_dict": parsed_output.dict(),
                           "parsed_output_string": str(parsed_output),
                           "messages": messages,
                           }}
        )
        student_initials = get_initials(entry["_student_name"])

        save_green_check_entry_to_markdown(base_summary_name="green_check_messages",
                                           text=str(parsed_output),
                                           file_name=f"{student_initials}_{parsed_output.summary_title}", )

        print(f"Student: {entry['_student_name']}: \n"
              f"Messages with green check: \n{messages}\n"
              f"Parsed output: \n{parsed_output}")

    if save_to_json:
        await mongo_database.save_json(collection_name=collection_name)


def save_green_check_entry_to_markdown(base_summary_name: str,
                                       text:str,
                                       file_name: str,
                                       subfolder: str = None,
                                       save_path: Union[str, Path] = None,
                                       ):
    load_dotenv()
    if not save_path:
        save_path = Path(
            os.getenv(
                "PATH_TO_COURSE_DROPBOX_FOLDER")) / "course_data" / "chatbot_data" / base_summary_name
    if subfolder:
        save_path = save_path / subfolder

    save_path.mkdir(parents=True, exist_ok=True)

    clean_file_name = file_name.replace(":", "_").replace(".", "_").replace(" ", "_")
    clean_file_name += ".md"

    save_path = save_path / clean_file_name

    with open(str(save_path), 'w', encoding='utf-8') as f:
        f.write(text)

    print(f"Markdown file generated and saved at {str(save_path)}.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(grab_green_check_messages(server_name="Neural Control of Real World Human Movement 2023 Summer1",
                                          overwrite=True,
                                          save_to_json=True,
                                          ))

    asyncio.run(parse_green_check_messages(collection_name="green_check_messages",
                                           overwrite=True,
                                           save_to_json=True,
                                           ))

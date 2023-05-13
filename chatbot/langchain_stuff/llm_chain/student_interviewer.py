import json

from dotenv import load_dotenv
from langchain import LLMChain
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import (
    HumanMessagePromptTemplate,
    ChatPromptTemplate, SystemMessagePromptTemplate,
)
from pydantic import BaseModel

NEURAL_CONTROL_OF_REAL_WORLD_HUMAN_MOVEMENT_COURSE_STUDENT_INTERVIEWER_TEMPLATE = """

            You are a teaching assistant for the course: Neural Control of Real-World Human Movement
            
            
            Course Description:
            In this interdisciplinary course, students will explore the neural basis of natural human behavior in real-world contexts (e.g., sports, dance, or everyday activities) by investigating the neural control of full-body human movement. The course will cover philosophical, technological, and scientific aspects related to the study of natural behavior while emphasizing hands-on, project-based learning. Students will use free open-source machine-learning and computer-vision-driven tools and methods to record human movement in unconstrained environments.
            
            The course promotes interdisciplinary collaboration and introduces modern techniques for decentralized project management, AI-assisted research techniques, and Python-based programming (No prior programming experience is required). Students will receive training in the use of AI technology for project management and research conduct, including literature review, data analysis, and presentation of results. Through experiential learning, students will develop valuable skills in planning and executing technology-driven research projects while examining the impact of structural inequities on scientific inquiry.
            The primary focus is on collaborative work where each student will contribute to a shared research project on their interests/skillsets (e.g. some students will do more programming, others will do more lit reviewing, etc).

            Course Objectives:
            - Gain exposure to key concepts related to neural control of human movement.
            - Apply interdisciplinary approaches when collaborating on complex problems.
            - Develop a basic understanding of machine-learning tools for recording human movements.
            - Contribute effectively within a team setting towards achieving common goals.
            - Acquire valuable skills in data analysis or background research.
            
            
        Your task is to: 
        
        Conduct a thoughtful and engaging interview with each student using the following schema: 
        
        #Student interview schema:
        
        class StudentInterviewSchema(BaseModel):
            major: str
            experience_level: str
            background: str
            interests: str
            hobbies: str
            what_part_of_this_class_are_you_most_excited_about: str
            what_part_of_this_class_are_you_most_nervous_about: str
            what_do_you_hope_to_learn: str
            programming_experience: str
            interest_in_programming: str
            scientific_literature_experience: str
            interest_in_scientific_literature: str
        
        You want to find out more about their previous exposure to the topics covered in this course, their goals for this course, and any specific areas of interest within the broad field of neural control of human movement. You're aiming to use this information to tailor your teaching and guidance to their individual needs, and to help create a collaborative and inclusive learning environment.                 
        
        Keep asking questions until you can fill out the schema above for the student you are talking to.
         
        When you think you have enough info to make a guess, offer it to the student and tell them to respond with a `??` if it is accurate, or to offer corrections if it is not.

       ----
        Chat history:            
        {chat_history}
        """


class StudentInterviewSchema(BaseModel):
    name: str
    major: str
    experience_level: str
    background: str
    interests: str
    hobbies: str
    what_part_of_this_class_are_you_most_excited_about: str
    what_part_of_this_class_are_you_most_nervous_about: str
    what_do_you_hope_to_learn: str
    programming_experience: str
    interest_in_programming: str
    scientific_literature_experience: str
    interest_in_scientific_literature: str

    def to_json(self) -> str:
        return json.dumps(self.dict(), indent=2)


class StudentInterviewer:
    def __init__(self, temperature=0.8, model_name="gpt-4"):
        load_dotenv()
        self._chat_llm = ChatOpenAI(
            streaming=True,
            callbacks=[StreamingStdOutCallbackHandler()],
            temperature=temperature,
            model_name=model_name,
        )
        self._chat_prompt = self._create_chat_prompt()
        self._memory = self._configure_memory()
        self._chain = self._create_llm_chain()

    def _configure_memory(self):
        return ConversationBufferMemory(memory_key="chat_history")

    def _create_llm_chain(self):
        return LLMChain(llm=self._chat_llm,
                        prompt=self._chat_prompt,
                        memory=self._memory,
                        verbose=True,
                        )

    def _create_chat_prompt(self):
        student_interview_parser = PydanticOutputParser(pydantic_object=StudentInterviewSchema)
        system_message_prompt = SystemMessagePromptTemplate.from_template(
            template=NEURAL_CONTROL_OF_REAL_WORLD_HUMAN_MOVEMENT_COURSE_STUDENT_INTERVIEWER_TEMPLATE,
        )
        human_template = "{human_input}"
        human_message_prompt = HumanMessagePromptTemplate.from_template(
            human_template
        )

        chat_prompt = ChatPromptTemplate.from_messages(
            [system_message_prompt, human_message_prompt]
        )
        return chat_prompt

    def process_input(self, input_text):
        print(f"Input: {input_text}")
        print("Streaming response...\n")
        response = self._chain.run(human_input=input_text)
        return response

    async def async_process_input(self, input_text):
        print(f"Input: {input_text}")
        print("Streaming response...\n")
        response = await self._chain.arun(human_input=input_text)
        return response

    def demo(self):
        print("Welcome to the Neural Control Assistant demo!")
        print("You can ask questions or provide input related to the course.")
        print("Type 'exit' to end the demo.\n")

        while True:
            input_text = input("Enter your input: ")

            if input_text.strip().lower() == "exit":
                print("Ending the demo. Goodbye!")
                break

            response = self.process_input(input_text)

            print("\n")


if __name__ == "__main__":
    assistant = StudentInterviewer()
    assistant.demo()
import logging
import asyncio
import os
import glob
from src.preprocessing.download_manager import DownloadManager
from src.preprocessing.video_processor import VideoProcessor
from src.preprocessing.transcript_generator import TranscriptGenerator
from src.preprocessing.file_processor import FileProcessor
from src.report_generation.openai_client import OpenAIClient
from src.report_generation.report_generator import ReportGenerator
import json
import sys

# Initialize logging
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
console_handler.stream.reconfigure(encoding="utf-8")  # This line ensures UTF-8 encoding

file_handler = logging.FileHandler("processing.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])


class MainFlow:
    def __init__(self, config_path: str):
        with open(config_path) as f:
            self.config = json.load(f)
        self.paths = self.config["PATHS"]
        self._create_directories()

    def _create_directories(self):
        for path in self.paths.values():
            os.makedirs(path, exist_ok=True)
        # Additional mentor directories
        os.makedirs(self.paths["MENTOR_ORIGINALS"], exist_ok=True)
        os.makedirs(self.paths["MENTOR_TRANSCRIPTS"], exist_ok=True)

    async def process_url(self, url: str):
        VideoProcessor.clean_directory(self.paths["DOWNLOAD"])
        VideoProcessor.clean_directory(self.paths["AUDIO"])

        # Collect base names of existing transcripts
        transcript_basenames = {
            os.path.splitext(f)[0]
            for f in os.listdir(self.paths["TRANSCRIPT"])
            if f.endswith(".txt")
        }

        download_manager = DownloadManager(self.paths["DOWNLOAD"])
        video_processor = VideoProcessor()
        transcript_generator = TranscriptGenerator(
            os.getenv("AZURE_SPEECH_KEY"),
            os.getenv("AZURE_SPEECH_REGION")
        )

        async for video_path in download_manager.download_videos(url, skip_basenames=transcript_basenames):
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            transcript_path = os.path.join(self.paths["TRANSCRIPT"], f"{base_name}.txt")

            audio_path = os.path.join(self.paths["AUDIO"], f"{base_name}.wav")

            if video_processor.convert_mp4_to_wav(video_path, audio_path):
                transcript_generator.transcribe_audio(audio_path, transcript_path)
            else:
                print(f"❌ Failed to convert video: {video_path}")

            # Cleanup
            os.remove(video_path)
            if os.path.exists(audio_path):
                os.remove(audio_path)
            else:
                logging.warning(f"Audio file not found for deletion: {audio_path}")

    def process_mentor_materials(self, mentor_dir: str):
        print("\nProcessing mentor materials...")

        # Collect base names of existing mentor transcripts
        mentor_transcript_basenames = {
            os.path.splitext(f)[0]
            for f in os.listdir(self.paths["MENTOR_TRANSCRIPTS"])
            if f.endswith(".txt")
        }

        # Process slide files
        for file_path in glob.glob(os.path.join(mentor_dir, "*.pptx")) + \
                         glob.glob(os.path.join(mentor_dir, "*.ppt")):
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            if base_name in mentor_transcript_basenames:
                logging.info(f"Transcript already exists for {base_name}, skipping slide file.")
                continue
            FileProcessor.process_slide_file(
                file_path,
                self.paths["MENTOR_ORIGINALS"],
                self.paths["MENTOR_TRANSCRIPTS"]
            )

        # Process notebook files
        for file_path in glob.glob(os.path.join(mentor_dir, "*.ipynb")):
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            if base_name in mentor_transcript_basenames:
                logging.info(f"Transcript already exists for {base_name}, skipping notebook file.")
                continue
            FileProcessor.process_notebook_file(
                file_path,
                self.paths["MENTOR_ORIGINALS"],
                self.paths["MENTOR_TRANSCRIPTS"]
            )

    def generate_quality_reports(self):
        print("\nGenerating quality reports...")
        # Load checklist
        with open("config/checklist.txt", "r") as f:
            checklist = f.read()

        # Initialize OpenAI client
        openai_client = OpenAIClient("config/config.json")
        client = openai_client.get_client()
        deployment = openai_client.get_deployment()

        report_generator = ReportGenerator(client, deployment, checklist)
        report_generator.generate_reports(
            self.paths["TRANSCRIPT"],
            self.paths["MENTOR_TRANSCRIPTS"],
            self.paths["REPORTS"]
        )
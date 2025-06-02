import shutil
import subprocess
import os

class VideoProcessor:
    @staticmethod
    def clean_directory(directory: str):
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

    @staticmethod
    def convert_mp4_to_wav(mp4_file_path: str, wav_file_path: str) -> bool:
        try:
            if not os.path.exists(mp4_file_path):
                print(f"Video file does not exist: {mp4_file_path}")
                return False
            if not shutil.which("ffmpeg"):
                print("ffmpeg is not installed or not in PATH.")
                return False
            command = [
                "ffmpeg",
                "-i", mp4_file_path,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-y",
                wav_file_path
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"ffmpeg error:\n{result.stderr}")
                return False
            return True
        except Exception as e:
            print(f"Conversion error: {str(e)}")
            return False
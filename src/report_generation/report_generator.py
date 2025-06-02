import os
import glob
import time
from typing import List, Tuple

class ReportGenerator:
    def __init__(self, openai_client, deployment_name: str, checklist: str):
        self.client = openai_client
        self.deployment_name = deployment_name
        self.checklist = checklist

    def quality_check(self, transcript_content: str, material_type: str, material_content: str = None) -> str:
        material_context = ""
        if material_content:
            if material_type == "slides":
                material_context = f"\n### SLIDE CONTENT ###\n{material_content}"
            elif material_type == "notebook":
                material_context = f"\n### NOTEBOOK CONTENT ###\n{material_content}"

        user_input = f"""
### VIDEO TRANSCRIPT ###
{transcript_content}
{material_context}

### TASK ###
Review using this checklist:
{self.checklist}

### INSTRUCTIONS ###
1. For EACH checklist item ():
   - For each item, respond on a new line using the format:
      1a: Topic and Subtopic Coverage: Confirm that all planned topics and subtopics are mentioned and explained. [✅]
      or
      2e: Demonstration Pacing: Hands-on activities should be taught at a followable pace. [❌] The demo moved too fast without explanation.
   - Respond with ✅ if satisfied
   - Respond with ❌ if not satisfied + 1-2 line explanation
   - Use 'N/A' only if completely inapplicable
2. For Code Walkthrough items (Section 2):
   - If no code in video, mark ALL 2a-2e as "N/A - No code walkthrough"
3. After checklist, provide:
   - "What Went Wrong:" (bullet points of main issues)
   - "How to Improve:" (bullet points of specific recommendations)
4. Use ONLY the format below

### REQUIRED RESPONSE FORMAT ###
1a: [✅/❌/N/A] [Brief explanation if ❌]
1b: [✅/❌/N/A] [Brief explanation if ❌]
...
8a: [✅/❌/N/A] [Brief explanation if ❌]

What Went Wrong:
- [Issue 1]
- [Issue 2]

How to Improve:
- [Recommendation 1]
- [Recommendation 2]
"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an analytical quality assurance assistant."},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.2,
                max_tokens=4096,
                top_p=0.95
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Azure OpenAI error: {str(e)}")
            return f"Error in quality check: {str(e)}"

    def get_all_transcripts(self, transcript_path: str, mentor_transcripts_path: str) -> Tuple[List[dict], List[dict]]:
        video_transcripts = []
        for file_path in glob.glob(os.path.join(transcript_path, "*.txt")):
            if not file_path.startswith(mentor_transcripts_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    video_transcripts.append({
                        "type": "video",
                        "path": file_path,
                        "content": f.read(),
                        "base_name": os.path.splitext(os.path.basename(file_path))[0]
                    })

        mentor_transcripts = []
        for file_path in glob.glob(os.path.join(mentor_transcripts_path, "*.txt")):
            with open(file_path, 'r', encoding='utf-8') as f:
                filename = os.path.basename(file_path)
                mentor_type = "slides" if "slide" in filename.lower() else "notebook"
                mentor_transcripts.append({
                    "type": mentor_type,
                    "path": file_path,
                    "content": f.read(),
                    "base_name": os.path.splitext(filename)[0]
                })

        return video_transcripts, mentor_transcripts

    def generate_reports(self, transcript_path: str, mentor_transcripts_path: str, reports_dir: str):
        video_transcripts, mentor_transcripts = self.get_all_transcripts(transcript_path, mentor_transcripts_path)

        if not video_transcripts:
            print("No video transcripts found!")
            return

        for video in video_transcripts:
            print(f"\nProcessing video: {os.path.basename(video['path'])}")

            slides_content = None
            notebook_content = None

            for material in mentor_transcripts:
                if material['base_name'] == video['base_name']:
                    if material['type'] == "slides":
                        slides_content = material['content']
                    elif material['type'] == "notebook":
                        notebook_content = material['content']

            material_content = slides_content or notebook_content
            material_type = "slides" if slides_content else ("notebook" if notebook_content else None)

            report = self.quality_check(video['content'], material_type, material_content)

            report_file = os.path.join(reports_dir, f"report_{video['base_name']}.txt")
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)

            print(f"✅ Report saved to {report_file}")
            time.sleep(2)
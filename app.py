import streamlit as st
import os
import asyncio
import logging
import sys
import tempfile
import shutil
import json
import glob
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# Add backend modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from preprocessing.download_manager import DownloadManager
from preprocessing.video_processor import VideoProcessor
from preprocessing.transcript_generator import TranscriptGenerator
from preprocessing.file_processor import FileProcessor
from report_generation.openai_client import OpenAIClient
from report_generation.report_generator import ReportGenerator
from main_flow import MainFlow

# Configuration setup
class AppConfig:
    def __init__(self):
        self.PATHS = {
            "DOWNLOAD": "downloads",
            "AUDIO": "audios",
            "TRANSCRIPT": "transcripts",
            "REPORTS": "reports",
            "MENTOR_ORIGINALS": "downloads/mentor_materials",
            "MENTOR_TRANSCRIPTS": "transcripts/mentor_materials"
        }
        self.ensure_directories()
        
    def ensure_directories(self):
        for path in self.PATHS.values():
            os.makedirs(path, exist_ok=True)

# Streamlit App
def main():
    st.set_page_config(
        page_title="QC Report Generator", 
        page_icon="📊", 
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS for styling
    st.markdown("""
        <style>
        .stProgress > div > div > div > div {
            background-color: #4CAF50;
        }
        .stButton button {
            background-color: #4CAF50 !important;
            color: white !important;
            font-weight: bold;
            padding: 10px 24px;
            border-radius: 5px;
            border: none;
            transition: all 0.3s;
        }
        .stButton button:hover {
            background-color: #45a049 !important;
            transform: scale(1.05);
        }
        .report-box {
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            padding: 20px;
            margin: 10px 0;
            background-color: #f9f9f9;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .success-banner {
            background-color: #d4edda;
            color: #155724;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
            text-align: center;
            font-size: 1.1em;
        }
        .header {
            background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 30px;
        }
        .step-card {
            background-color: #f0f8ff;
            border-left: 4px solid #4CAF50;
            padding: 15px;
            margin: 10px 0;
            border-radius: 0 8px 8px 0;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Initialize session state
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'reports_generated' not in st.session_state:
        st.session_state.reports_generated = False
    if 'mentor_dir' not in st.session_state:
        st.session_state.mentor_dir = tempfile.mkdtemp(prefix="mentor_")
    if 'main_flow' not in st.session_state:
        st.session_state.main_flow = MainFlow("config/config.json")
    
    # App header
    st.markdown("""
        <div class="header">
            <h1>📊 QC Report Generator</h1>
            <p>Automated Quality Control for Training Materials</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Create columns for layout
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("🔧 Configuration")
        
        # Box link input
        box_link = st.text_input("Enter Box Link:", 
                                placeholder="https://greatlearningcontent.app.box.com/s/...",
                                help="URL to the Box folder containing training videos")
        
        # QC type selection
        qc_type = st.selectbox(
            "Select QC Type:",
            ["", "Conceptual", "Hands-on", "Both"],
            index=0,
            help="Select the type of quality check to perform"
        )
        
        # File uploaders based on QC type
        ppt_file = None
        notebook_file = None
        
        if qc_type in ["Conceptual", "Both"]:
            ppt_file = st.file_uploader("Upload Presentation File:", 
                                       type=["ppt", "pptx"], 
                                       help="Upload PowerPoint file for conceptual QC")
        
        if qc_type in ["Hands-on", "Both"]:
            notebook_file = st.file_uploader("Upload Notebook File:", 
                                           type=["ipynb"], 
                                           help="Upload Jupyter Notebook for hands-on QC")
        
        # Generate report button
        if st.button("Generate Report", disabled=st.session_state.processing):
            if not box_link:
                st.error("Please enter a Box link")
                return
            if not qc_type:
                st.error("Please select a QC type")
                return
            if qc_type in ["Conceptual", "Both"] and ppt_file is None:
                st.error("Please upload a PPT file")
                return
            if qc_type in ["Hands-on", "Both"] and notebook_file is None:
                st.error("Please upload a Notebook file")
                return
                
            st.session_state.processing = True
            st.session_state.reports_generated = False
            st.rerun()
    
    with col2:
        st.subheader("🚀 Processing Status")
        
        # Show processing status if in progress
        if st.session_state.processing:
            status_container = st.container()
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Create a temporary mentor directory
            mentor_dir = st.session_state.mentor_dir
            os.makedirs(mentor_dir, exist_ok=True)
            
            # Save uploaded files
            if ppt_file:
                ppt_path = os.path.join(mentor_dir, ppt_file.name)
                with open(ppt_path, "wb") as f:
                    f.write(ppt_file.getbuffer())
            
            if notebook_file:
                notebook_path = os.path.join(mentor_dir, notebook_file.name)
                with open(notebook_path, "wb") as f:
                    f.write(notebook_file.getbuffer())
            
            # Initialize progress tracking
            progress_steps = {
                "download": 0,
                "mentor": 0,
                "transcribe": 0,
                "report": 0
            }
            
            # Start processing
            status_text.markdown("""
                <div class="step-card">
                    <h3>Starting processing pipeline...</h3>
                </div>
            """, unsafe_allow_html=True)
            
            # Step 1: Process URL
            status_text.markdown("""
                <div class="step-card">
                    <h3>Step 1/4: Downloading videos from Box...</h3>
                </div>
            """, unsafe_allow_html=True)

            try:
                # Create a new event loop for async processing
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # Process URL
                loop.run_until_complete(
                    st.session_state.main_flow.process_url(box_link)
                )
                progress_bar.progress(25)
            except Exception as e:
                status_text.error(f"Error downloading videos: {str(e)}")
                st.session_state.processing = False
                return
                # Create a new event loop for async processing
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Process URL
                loop.run_until_complete(
                    st.session_state.main_flow.process_url(box_link)
                )
                progress_bar.progress(25)
            except Exception as e:
                status_text.error(f"Error downloading videos: {str(e)}")
                st.session_state.processing = False
                return
            
            # Step 2: Process mentor materials
            status_text.markdown("""
                <div class="step-card">
                    <h3>Step 2/4: Processing mentor materials...</h3>
                </div>
            """, unsafe_allow_html=True)
            
            try:
                st.session_state.main_flow.process_mentor_materials(mentor_dir)
                progress_bar.progress(50)
            except Exception as e:
                status_text.error(f"Error processing mentor materials: {str(e)}")
                st.session_state.processing = False
                return
            
            # Step 3: Generate transcripts
            status_text.markdown("""
                <div class="step-card">
                    <h3>Step 3/4: Generating transcripts...</h3>
                </div>
            """, unsafe_allow_html=True)
            
            try:
                # This step happens automatically in the background
                # during the main flow processing
                progress_bar.progress(75)
            except Exception as e:
                status_text.error(f"Error generating transcripts: {str(e)}")
                st.session_state.processing = False
                return
            
            # Step 4: Generate reports
            status_text.markdown("""
                <div class="step-card">
                    <h3>Step 4/4: Generating quality reports...</h3>
                </div>
            """, unsafe_allow_html=True)
            
            try:
                st.session_state.main_flow.generate_quality_reports()
                progress_bar.progress(100)
            except Exception as e:
                status_text.error(f"Error generating reports: {str(e)}")
                st.session_state.processing = False
                return
            
            status_text.markdown("""
                <div class="step-card">
                    <h3>✅ Processing completed successfully!</h3>
                </div>
            """, unsafe_allow_html=True)
            
            st.session_state.processing = False
            st.session_state.reports_generated = True
            st.rerun()
        
        elif st.session_state.reports_generated:
            st.markdown('<div class="success-banner">✅ Reports generated successfully!</div>', unsafe_allow_html=True)
            st.balloons()
    
    # Show reports section
    st.divider()
    st.subheader("📋 Generated Reports")
    
    # Display reports if available
    config = AppConfig()
    reports_dir = config.PATHS["REPORTS"]
    report_files = glob.glob(os.path.join(reports_dir, "*.txt"))
    
    if report_files:
        for report_file in report_files:
            report_name = os.path.basename(report_file)
            with st.expander(f"📝 {report_name.replace('_', ' ').replace('.txt', '')}", expanded=False):
                try:
                    with open(report_file, "r", encoding="utf-8") as f:
                        report_content = f.read()
                    
                    st.markdown(f"<div class='report-box'>{report_content}</div>", unsafe_allow_html=True)
                    
                    st.download_button(
                        label=f"Download {report_name}",
                        data=report_content,
                        file_name=report_name,
                        mime="text/plain",
                        key=f"dl_{report_name}"
                    )
                except UnicodeDecodeError:
                    st.error(f"Could not read report {report_name} due to encoding issues")
    else:
        st.info("No reports generated yet. Submit a request to generate QC reports.")

if __name__ == "__main__":
    main()
import asyncio
import os
import logging
import sys
from dotenv import load_dotenv
from src.main_flow import MainFlow

# Load environment variables
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

async def main():
    try:
        # Initialize main flow
        main_flow = MainFlow("config/config.json")
        
        # Step 1: Process URL
        logging.info("Starting video processing...")
        await main_flow.process_url("https://greatlearningcontent.app.box.com/s/i6zeycc9pch4n0x27bv2rhum23rh1i8q")
        
        # Step 2: Process mentor materials
        mentor_dir = "mentor files"  # UPDATE THIS PATH
        logging.info("Processing mentor materials...")
        main_flow.process_mentor_materials(mentor_dir)
        
        # Step 3: Generate reports
        logging.info("Generating quality reports...")
        main_flow.generate_quality_reports()
        
        logging.info("\n✅ Processing completed!")
    except Exception as e:
        logging.error(f"🚨 Critical error in main flow: {str(e)}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
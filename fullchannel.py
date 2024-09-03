import yt_dlp as youtube_dl
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound
from openai import OpenAI
import os
import time
import re
import json
from dotenv import load_dotenv
from googleapiclient.discovery import build

# Load environment variables from .env file
load_dotenv()
api_key = os.getenv('OPENAI_API_KEY')
youtube_api_key = os.getenv('YOUTUBE_API_KEY')

client = OpenAI(api_key=api_key)
youtube = build('youtube', 'v3', developerKey=youtube_api_key)

def fetch_transcription(video_id):
    start_time = time.time()
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        transcription = " ".join([entry['text'] for entry in transcript_list])
        print("Transcription fetched successfully.")
    except NoTranscriptFound:
        print("No transcript found for this video.")
        transcription = None
    except Exception as e:
        print(f"Error fetching transcription: {e}")
        transcription = None

    end_time = time.time()
    print(f"Fetching transcription took {end_time - start_time:.2f} seconds")
    return transcription

def fetch_video_info(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best'
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        title = info_dict.get('title', 'Unknown Title')
        return title

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def create_thread():
    try:
        thread = client.beta.threads.create()
        print(f"Thread created successfully: {thread.id}")
        return thread.id
    except Exception as e:
        print("Error creating Thread:", e)
        return None

def add_message_to_thread(thread_id, content):
    try:
        message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content
        )
        print(f"Message added to Thread successfully.")
        return message
    except Exception as e:
        print("Error adding message to Thread:", e)
        return None

def create_and_poll_run(thread_id, instructions):
    try:
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id="asst_mPDA2MU2oNcgPyNa2LnssJsQ",  # Replace with your existing assistant ID
            instructions=instructions,
            response_format="auto"
        )
        print(f"Run created and completed successfully: {run.id}")

        messages = client.beta.threads.messages.list(
            thread_id=thread_id
        )

        for message in messages:
            if message.role == 'assistant':
                response_text = message.content[0].text.value
                print("\nAssistant Response:")
                print(response_text)
                if response_text.strip():
                    return response_text
                else:
                    print("Received an empty response.")
                    return None
    except Exception as e:
        print("Error creating and polling Run:", e)
        return None

def summarize_text_with_chatgpt(transcripts_with_titles):
    combined_text = "\n\n".join(transcripts_with_titles)
    thread_id = create_thread()
    if not thread_id:
        return "Error creating thread."

    detailed_instructions = (
        """You are an entrepreneur scouring the web for business ideas. You look through the transcripts given for any profitable idea. These ideas can be investment opportunities, personal finance, business, budgeting, advanced trading techniques, soloprenuership, startups, saas, individual projects. Find all
          pieces of information in these transcripts that could help you make a profit or build a business. 
          
          Please give 1-3 actionable steps for each video transcript. Focus should be on business ideas and opportunities.
        """
    )

    add_message_to_thread(thread_id, f"\n\n{combined_text}")
    summary = create_and_poll_run(thread_id, detailed_instructions)
    return summary

def get_channel_name(channel_id):
    try:
        response = youtube.channels().list(
            part='snippet',
            id=channel_id
        ).execute()
        
        if 'items' not in response or not response['items']:
            raise ValueError("No items found in the response")
        
        channel_name = response['items'][0]['snippet']['title']
        return channel_name
    except Exception as e:
        print(f"Failed to get channel name: {e}")
        return None

def read_video_links(file_path):
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r") as f:
        return json.load(f)

def write_video_links(file_path, video_links):
    with open(file_path, "w") as f:
        json.dump(video_links, f, indent=4)

if __name__ == "__main__":
    channel_id = 'UCUyDOdBWhC1MCxEjC46d-zw'  # Example channel ID
    channel_name = get_channel_name(channel_id)
    if not channel_name:
        print("Failed to get channel name.")
        exit(1)

    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    output_file = os.path.join(output_dir, f"{sanitize_filename(channel_name)}.txt")
    video_links_file = os.path.join(output_dir, "video_links.json")

    for i in range(10):  # Loop 10 times
        video_links = read_video_links(video_links_file)

        transcripts_with_titles = []
        for url, data in video_links.items():
            if not data["analyzed"]:
                video_id = url.split("v=")[-1]
                transcript = fetch_transcription(video_id)
                if transcript:
                    title = fetch_video_info(url)
                    transcripts_with_titles.append(f"Title: {title}\n\n{transcript}")
                    video_links[url]["analyzed"] = True
                    if len(transcripts_with_titles) >= 10:  # Process 5 videos at a time
                        break

        if transcripts_with_titles:
            summary = summarize_text_with_chatgpt(transcripts_with_titles)
            if summary:  # Check if summary is not None
                with open(output_file, "a") as f:
                    f.write("Summary:\n")
                    f.write(summary)
                    f.write("\n\n" + "="*80 + "\n\n")  # Separator between summaries
                print(f"Summary appended to {output_file}")
            else:
                print("No summary generated.")

        # Ensure the JSON file is updated with the analyzed status
        write_video_links(video_links_file, video_links)
from google import genai
import os
from google.api_core import exceptions
import time

# 1. Setup - Replace with your NEW API key
# Best practice: use os.environ.get("GEMINI_API_KEY")
API_KEY = "AIzaSyB5-x4k_7o6ieWz8PX_SRKyUMlNA7fMBfs" 

client = genai.Client(api_key=API_KEY)

def send_message_with_retry(chat, message):
    retries = 5
    for i in range(retries):
        try:
            return chat.send_message(message)
        except exceptions.ResourceExhausted:
            wait_time = (2 ** i) + 1  # Exponential backoff: 1, 3, 5, 9, 17 seconds
            print(f"Quota reached. Retrying in {wait_time}s...")
            time.sleep(wait_time)
    raise Exception("Still failing after max retries.")

def start_chat():
    # 2. Initialize the chat session
    # Using 'gemini-2.0-flash' for fast, smart responses
    chat = client.chats.create(model="gemini-2.5-flash")
    
    print("--- Gemini Chatbot (Type 'quit' to exit) ---")
    
    while True:
        user_input = input("You: ")
        
        if user_input.lower() in ['quit', 'exit', 'bye']:
            print("Gemini: Goodbye!")
            break
            
        try:
            print(user_input)
            # 3. Send message and get response
            response = chat.send_message(user_input)
            print(f"Gemini: {response.text}")
            
        except Exception as e:
            print(f"Error: {e}")
            response = send_message_with_retry(chat, user_input)
            print(f"Gemini: {response.text}")

if __name__ == "__main__":
    start_chat()
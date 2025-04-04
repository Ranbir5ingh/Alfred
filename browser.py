import speech_recognition as sr
import pyttsx3
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import threading
import google.generativeai as genai
import os
import re
import json
from selenium.common.exceptions import ElementNotInteractableException, StaleElementReferenceException, TimeoutException

# Initialize the speech recognizer and text-to-speech engine
recognizer = sr.Recognizer()
engine = pyttsx3.init()
scrolling_active = False
command_received = None

# Configure Gemini API
GEMINI_API_KEY = "AIzaSyB0HeJ3JJBAU_LiwIsQcZVnIJUtiefY6JQ"  # Replace with your actual API key
genai.configure(api_key=GEMINI_API_KEY)

# Initialize Gemini model
model = genai.GenerativeModel('gemini-2.0-flash')

# Function to speak text
def speak(text):
    engine.say(text)
    engine.runAndWait()

# Function to listen for voice commands in a separate thread
def listen_thread():
    global command_received
    while True:
        with sr.Microphone() as source:
            print("Listening...")
            audio = recognizer.listen(source)
            try:
                command = recognizer.recognize_google(audio)
                print(f"You said: {command}")
                command_received = command.lower()
            except sr.UnknownValueError:
                print("Sorry, I did not understand that.")
            except sr.RequestError:
                print("Could not request results from Google Speech Recognition service.")
        time.sleep(0.1)  # Small pause to prevent CPU overuse

# Function to process natural language with Gemini AI
def process_with_gemini(command):
    prompt = f"""
    I am a voice-controlled browser assistant. Parse the following command and return a JSON object with:
    1. "intent": The primary action being requested (open_website, search, scroll, navigate, click, etc.)
    2. "target": The target website, search query, or element
    3. "parameters": Any additional parameters
    
    Command: "{command}"
    
    For website requests like "open YouTube", set:
    - intent: "open_website"
    - target: "youtube.com"
    
    For scrolling commands, use these exact values for target:
    - "start" for "start scrolling"
    - "stop" for "stop scrolling"
    - "top" for "scroll to top"
    - "bottom" for "scroll to bottom"
    - "up" for scrolling upward
    - "down" for scrolling downward
    - "pause" for pausing scrolling
    - "continue" for continuing scrolling
    
    For search requests, extract the search query.
    
    Return ONLY the JSON object with no additional text.
    """
    
    try:
        response = model.generate_content(prompt)
        result = response.text.strip()
        
        # Extract the JSON object if it's wrapped in code blocks
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', result, re.DOTALL)
        if json_match:
            result = json_match.group(1)
        
        # Parse the JSON
        parsed_result = json.loads(result)
        
        # Debug the parsed result
        print(f"Parsed result: {parsed_result}")
        
        # Handle common website names directly to avoid search confusion
        if parsed_result["intent"] == "open_website":
            website_map = {
                "youtube": "youtube.com",
                "google": "google.com",
                "facebook": "facebook.com",
                "twitter": "twitter.com",
                "instagram": "instagram.com",
                "linkedin": "linkedin.com",
                "reddit": "reddit.com",
                "amazon": "amazon.com",
                "netflix": "netflix.com"
            }
            
            # Check if target is a simple website name that should be mapped
            for simple_name, domain in website_map.items():
                if simple_name in parsed_result["target"].lower():
                    parsed_result["target"] = domain
                    break
        
        # Fix common scrolling command issues
        if parsed_result["intent"] == "scroll":
            scrolling_targets = ["scroll_start", "scroll_stop", "scroll_top", "scroll_bottom", 
                                "start_scrolling", "stop_scrolling", "scroll_up", "scroll_down",
                                "scrolling_start", "scrolling_stop"]
            
            if parsed_result["target"] in scrolling_targets:
                # Map to expected targets
                if "start" in parsed_result["target"] or "down" in parsed_result["target"]:
                    parsed_result["target"] = "start"
                elif "stop" in parsed_result["target"]:
                    parsed_result["target"] = "stop"
                elif "top" in parsed_result["target"]:
                    parsed_result["target"] = "top"
                elif "bottom" in parsed_result["target"]:
                    parsed_result["target"] = "bottom"
                elif "up" in parsed_result["target"]:
                    parsed_result["target"] = "up"
                    
        return parsed_result
    except Exception as e:
        print(f"Error processing with Gemini: {e}")
        return {"intent": "unknown", "target": None, "parameters": {}}

# Function to get window height
def window_height(driver):
    return driver.execute_script("return window.innerHeight;")

# Function to continuously scroll smoothly - FIXED VERSION
def continuous_scroll(driver, direction="down", pause_time=0.1, scroll_increment=100):
    global scrolling_active, command_received
    scrolling_active = True
    
    # Set scroll direction
    increment = scroll_increment if direction == "down" else -scroll_increment
    
    print(f"Starting continuous scrolling ({direction})...")
    speak(f"Starting continuous scrolling {direction}.")
    
    reported_bottom = False
    reported_top = False
    
    while scrolling_active:
        # Check for commands
        if command_received:
            parsed_command = process_with_gemini(command_received)
            if parsed_command["intent"] == "scroll":
                if parsed_command["target"] == "stop":
                    speak("Scrolling stopped.")
                    scrolling_active = False
                    return
                elif parsed_command["target"] == "top":
                    driver.execute_script("window.scrollTo(0, 0);")
                    speak("Scrolled to top.")
                    scrolling_active = False
                    return
                elif parsed_command["target"] == "bottom":
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    speak("Scrolled to bottom.")
                    scrolling_active = False
                    return
                elif parsed_command["target"] == "pause":
                    speak("Scrolling paused. Say 'continue scrolling' to resume.")
                    scrolling_active = False
                    # Wait for continue command
                    while not scrolling_active:
                        if command_received:
                            parsed_pause_command = process_with_gemini(command_received)
                            if parsed_pause_command["intent"] == "scroll" and parsed_pause_command["target"] == "continue":
                                speak("Resuming scrolling.")
                                scrolling_active = True
                            elif parsed_pause_command["intent"] == "scroll" and parsed_pause_command["target"] == "stop":
                                speak("Stopping scrolling.")
                                return
                            command_received = None
                        time.sleep(0.1)
            command_received = None
            
        # Get current scroll position before scrolling
        current_position = driver.execute_script("return window.pageYOffset;")
        
        # Scroll by the increment
        driver.execute_script(f"window.scrollBy(0, {increment});")
        
        # Wait for new content to load
        time.sleep(pause_time)
        
        # Get new position and page height
        new_position = driver.execute_script("return window.pageYOffset;")
        page_height = driver.execute_script("return document.body.scrollHeight;")
        
        # Check if we've reached the bottom or top
        if direction == "down" and new_position + window_height(driver) >= page_height - 50:
            # We've reached the bottom, go back to top and continue
            if not reported_bottom:
                speak("Reached bottom of page. Going back to top.")
                reported_bottom = True
            driver.execute_script("window.scrollTo(0, 0);")
            reported_top = False  # Reset the top report flag
            time.sleep(0.5)  # Pause briefly at the top
        elif direction == "up" and new_position <= 0:
            # We've reached the top, go to bottom and continue
            if not reported_top:
                speak("Reached top of page. Going to bottom.")
                reported_top = True
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            reported_bottom = False  # Reset the bottom report flag
            time.sleep(0.5)  # Pause briefly at the bottom
        else:
            # Reset report flags when we're not at the edges
            if new_position > 0 and new_position + window_height(driver) < page_height - 50:
                reported_bottom = False
                reported_top = False

# Function to open a website
def open_website(driver, website):
    # Check if the website already includes http:// or https://
    if not website.startswith(('http://', 'https://')):
        # Check if it's a domain name
        if '.' in website and ' ' not in website:
            url = 'https://' + website
        else:
            # Add .com if it appears to be a simple website name
            if ' ' not in website:
                url = 'https://' + website + '.com'
            else:
                # It's not a URL, search for it on Bing
                url = f"https://www.bing.com/search?q={website.replace(' ', '+')}"
    else:
        url = website
    
    try:
        print(f"Opening URL: {url}")
        driver.get(url)
        speak(f"Opening {website}")
        return True
    except Exception as e:
        speak(f"Error opening {website}")
        print(f"Error: {e}")
        return False

# Function to perform search on current website with improved error handling
def perform_search(driver, query):
    try:
        # First, try Google's search if we're on Google
        if "google.com" in driver.current_url:
            try:
                # Direct approach for Google search
                search_box = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.NAME, "q"))
                )
                search_box.clear()
                search_box.send_keys(query)
                search_box.send_keys(Keys.RETURN)
                speak(f"Searching for {query} on Google")
                return True
            except Exception as e:
                print(f"Google-specific search failed: {e}")
                # Fall through to generic approach
        
        # Try YouTube's search if we're on YouTube
        if "youtube.com" in driver.current_url:
            try:
                # Direct approach for YouTube search
                search_box = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.NAME, "search_query"))
                )
                search_box.clear()
                search_box.send_keys(query)
                search_box.send_keys(Keys.RETURN)
                speak(f"Searching for {query} on YouTube")
                return True
            except Exception as e:
                print(f"YouTube-specific search failed: {e}")
                # Fall through to generic approach
                
        # General approach - try multiple common search box identifiers with WebDriverWait
        search_selectors = [
            (By.XPATH, "//input[@type='search']"),
            (By.XPATH, "//input[@name='q']"),
            (By.XPATH, "//input[@name='search']"),
            (By.XPATH, "//input[contains(@placeholder, 'search') or contains(@placeholder, 'Search')]"),
            (By.XPATH, "//input[contains(@aria-label, 'search') or contains(@aria-label, 'Search')]"),
            (By.XPATH, "//input[contains(@class, 'search') or contains(@id, 'search')]"),
            (By.CSS_SELECTOR, "input[type='search']"),
            (By.CSS_SELECTOR, "input.search"),
            (By.CSS_SELECTOR, "input#search")
        ]
        
        for selector_type, selector in search_selectors:
            try:
                print(f"Trying selector: {selector_type} = {selector}")
                search_box = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((selector_type, selector))
                )
                # We found a search box, let's use it
                search_box.clear()
                search_box.send_keys(query)
                search_box.send_keys(Keys.RETURN)
                speak(f"Searching for {query}")
                return True
            except (TimeoutException, ElementNotInteractableException, StaleElementReferenceException) as e:
                print(f"Selector {selector} failed: {e}")
                continue  # Try the next selector
        
        # If no search box was found or usable, fallback to direct Bing search
        print("No usable search box found, falling back to Bing search")
        driver.get(f"https://www.bing.com/search?q={query.replace(' ', '+')}")
        speak(f"Searching for {query} on Bing")
        return True
            
    except Exception as e:
        speak(f"Error performing search")
        print(f"Error: {e}")
        # Fallback to Bing search on error
        try:
            driver.get(f"https://www.bing.com/search?q={query.replace(' ', '+')}")
            speak(f"Searching for {query} on Bing")
            return True
        except Exception as e2:
            print(f"Fallback search also failed: {e2}")
            return False

# Function to click on a link or element containing text
def click_element_with_text(driver, text):
    try:
        # Try multiple strategies to find clickable elements
        xpath_strategies = [
            f"//*[contains(text(), '{text}')]",
            f"//a[contains(text(), '{text}')]",
            f"//button[contains(text(), '{text}')]",
            f"//a[contains(@href, '{text}') or contains(@title, '{text}')]",
            f"//*[contains(@aria-label, '{text}')]",
            f"//*[contains(@title, '{text}')]",
            f"//*[contains(@alt, '{text}')]"
        ]
        
        for xpath in xpath_strategies:
            try:
                print(f"Trying to find element with xpath: {xpath}")
                element = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                element.click()
                speak(f"Clicked on {text}")
                return True
            except (TimeoutException, ElementNotInteractableException, StaleElementReferenceException) as e:
                print(f"XPath {xpath} failed: {e}")
                continue
        
        # If we haven't returned yet, we couldn't find a clickable element
        speak(f"Could not find clickable element containing {text}")
        return False
        
    except Exception as e:
        speak(f"Error clicking element")
        print(f"Error: {e}")
        return False

# Main function to handle voice commands and control the browser
def voice_controlled_browser():
    global command_received, scrolling_active
    # Start the listening thread
    listen_thread_instance = threading.Thread(target=listen_thread, daemon=True)
    listen_thread_instance.start()
    
    # Set up the Selenium WebDriver with options
    options = webdriver.EdgeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    service = Service(executable_path=r'C:\Users\ranbi\Downloads\edgedriver_win64\msedgedriver.exe')  # Update the path
    driver = webdriver.Edge(service=service, options=options)
    
    # Open a blank page to start
    driver.get("about:blank")
    speak("Voice-controlled browser is ready. What would you like to do?")
    
    scroll_thread = None
    
    while True:
        if command_received:
            # Process the command with Gemini API
            parsed_command = process_with_gemini(command_received)
            print(f"Parsed command: {parsed_command}")
            
            intent = parsed_command.get("intent", "unknown")
            target = parsed_command.get("target", "")
            parameters = parsed_command.get("parameters", {})
            
            # Handle different intents
            if intent == "open_website":
                open_website(driver, target)
                
            elif intent == "search":
                perform_search(driver, target)
                
            elif intent == "scroll":
                if target == "start" or target == "down":
                    speak("Starting continuous scrolling down.")
                    if scroll_thread and scroll_thread.is_alive():
                        scrolling_active = False
                        time.sleep(0.5)  # Wait for previous thread to terminate
                    scrolling_active = True
                    scroll_thread = threading.Thread(target=continuous_scroll, args=(driver, "down"), daemon=True)
                    scroll_thread.start()
                elif target == "up":
                    speak("Starting continuous scrolling up.")
                    if scroll_thread and scroll_thread.is_alive():
                        scrolling_active = False
                        time.sleep(0.5)  # Wait for previous thread to terminate
                    scrolling_active = True
                    scroll_thread = threading.Thread(target=continuous_scroll, args=(driver, "up"), daemon=True)
                    scroll_thread.start()
                elif target == "stop":
                    scrolling_active = False
                    speak("Scrolling stopped.")
                elif target == "top":
                    driver.execute_script("window.scrollTo(0, 0);")
                    speak("Scrolled to top.")
                elif target == "bottom":
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    speak("Scrolled to bottom.")
                    
            elif intent == "navigate":
                if target == "back":
                    driver.back()
                    speak("Going back.")
                elif target == "forward":
                    driver.forward()
                    speak("Going forward.")
                elif target == "refresh":
                    driver.refresh()
                    speak("Refreshing page.")
                    
            elif intent == "click":
                click_element_with_text(driver, target)
                
            elif intent == "exit" or intent == "quit":
                speak("Exiting the browser.")
                scrolling_active = False  # Stop any scrolling threads
                if scroll_thread and scroll_thread.is_alive():
                    time.sleep(0.5)  # Give thread time to terminate
                driver.quit()
                break
                
            elif intent == "unknown":
                speak("I'm not sure how to handle that command. Please try again.")
                
            command_received = None
        
        time.sleep(0.1)  # Small pause to prevent CPU overuse

if __name__ == "__main__":
    speak("Advanced voice-controlled browser automation is starting.")
    voice_controlled_browser()
import streamlit as st
import PyPDF2
from google import genai
import os
import tempfile
from PIL import Image
import pdf2image
import io
import numpy as np
import pytesseract
import hashlib
from datetime import datetime
import pandas as pd
import re

# Configure tesseract for Streamlit Cloud
if os.path.exists('/usr/bin/tesseract'):
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
elif os.path.exists('/app/.apt/usr/bin/tesseract'):
    pytesseract.pytesseract.tesseract_cmd = '/app/.apt/usr/bin/tesseract'

# Set page configuration
st.set_page_config(page_title="PDF Tender", layout="wide")

# Authentication functions
def check_credentials(username, password):
    """Check if provided credentials are valid"""
    try:
        # Get credentials from secrets
        valid_username = st.secrets["auth"]["username"]
        valid_password = st.secrets["auth"]["password"]
        
        # Check username and password
        return username == valid_username and password == valid_password
    except KeyError:
        st.error("Authentication configuration not found in secrets.")
        return False

def login_form():
    """Display login form"""
    st.title("Document Analyser - Login")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")
        
        if submit_button:
            if check_credentials(username, password):
                st.session_state.authenticated = True
                st.session_state.username = username
                st.rerun()
            else:
                st.error("Invalid username or password")

def logout():
    """Logout function"""
    st.session_state.authenticated = False
    st.session_state.username = None
    if 'pdf_text' in st.session_state:
        del st.session_state.pdf_text
    if 'file_name' in st.session_state:
        del st.session_state.file_name
    if 'chat_history' in st.session_state:
        del st.session_state.chat_history
    st.rerun()

def extract_csv_from_text(text):
    """Extract CSV content from text that contains ```csv blocks"""
    csv_pattern = r'```csv\s*\n(.*?)\n```'
    matches = re.findall(csv_pattern, text, re.DOTALL)
    return matches

def display_csv_content(csv_content, chat_index, csv_index):
    """Display CSV content as a table with download option"""
    try:
        # Parse CSV content
        csv_io = io.StringIO(csv_content)
        df = pd.read_csv(csv_io)
        
        # Display the table
        st.dataframe(df, use_container_width=True)
        
        # Create download button
        csv_bytes = csv_content.encode('utf-8')
        filename = f"extracted_data_{chat_index}_{csv_index}.csv"
        
        st.download_button(
            label="Download CSV",
            data=csv_bytes,
            file_name=filename,
            mime="text/csv",
            key=f"download_{chat_index}_{csv_index}"
        )
        
    except Exception as e:
        st.error(f"Error parsing CSV: {e}")
        st.text("Raw CSV content:")
        st.code(csv_content, language='csv')

def process_answer_with_csv(answer, chat_index):
    """Process answer to extract and display CSV content"""
    # Extract CSV blocks
    csv_blocks = extract_csv_from_text(answer)
    
    if csv_blocks:
        # Split the answer into parts
        parts = re.split(r'```csv\s*\n.*?\n```', answer, flags=re.DOTALL)
        
        # Display text and CSV blocks alternately
        for i, part in enumerate(parts):
            if part.strip():
                st.markdown(part.strip())
            
            # Display CSV block if it exists
            if i < len(csv_blocks):
                st.subheader(f"Data Table {i + 1}")
                display_csv_content(csv_blocks[i], chat_index, i)
                st.markdown("---")
    else:
        # No CSV blocks found, display as regular text
        st.markdown(answer)

def add_to_chat_history(question, answer):
    """Add a question-answer pair to chat history"""
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    chat_entry = {
        'question': question,
        'answer': answer,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    st.session_state.chat_history.append(chat_entry)

def display_chat_history():
    """Display the chat history with CSV processing"""
    if 'chat_history' in st.session_state and st.session_state.chat_history:
        st.subheader("Chat History")
        
        # Display in reverse order (newest first)
        for idx, chat in enumerate(reversed(st.session_state.chat_history)):
            chat_index = len(st.session_state.chat_history) - idx - 1
            
            # Create an expander for each chat entry
            with st.expander(f"Q: {chat['question'][:100]}{'...' if len(chat['question']) > 100 else ''}", expanded=(idx == 0)):
                st.markdown(f"**Question:** {chat['question']}")
                st.markdown(f"**Asked at:** {chat['timestamp']}")
                st.markdown("**Answer:**")
                
                # Process the answer for CSV content
                process_answer_with_csv(chat['answer'], chat_index)

# Initialize session state for authentication
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'username' not in st.session_state:
    st.session_state.username = None

# Check authentication
if not st.session_state.authenticated:
    login_form()
    st.stop()

# Main application (only shown if authenticated)
st.write(f"Welcome, {st.session_state.username}!")
if st.button("Logout"):
    logout()

# App title and description
st.title("Document Analyser")

# Initialize session state variables if they don't exist
if 'pdf_text' not in st.session_state:
    st.session_state.pdf_text = ""
if 'file_name' not in st.session_state:
    st.session_state.file_name = ""
if 'gemini_model' not in st.session_state:
    st.session_state.gemini_model = None
if 'api_key_configured' not in st.session_state:
    st.session_state.api_key_configured = False
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

try:
    api_key = st.secrets["api_key"]
except KeyError:
    st.error("API key not found in secrets configuration.")
    st.stop()

# Function to extract text from PDF
def extract_text_from_pdf(pdf_file):
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text += page.extract_text()
    return text

# Function to perform OCR on PDF using pytesseract
def perform_ocr_on_pdf(pdf_file):
    """
    Perform OCR on PDF using pytesseract and pdf2image
    """
    try:
        # Convert PDF to images
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(pdf_file.getvalue())
            tmp_path = tmp_file.name

        # Convert PDF pages to images
        pages = pdf2image.convert_from_bytes(pdf_file.getvalue())

        ocr_text = ""

        for page_num, page in enumerate(pages):
            # Convert PIL Image to RGB (pytesseract expects this)
            page_rgb = page.convert('RGB')
            # Perform OCR on the page
            page_text = pytesseract.image_to_string(page_rgb)
            ocr_text += f"\n--- Page {page_num + 1} ---\n"
            ocr_text += page_text

        # Clean up temporary file
        os.unlink(tmp_path)

        return ocr_text

    except Exception as e:
        st.error(f"OCR Error: {e}")
        return ""

# Function to configure Gemini API
def configure_gemini_api():
    if api_key and api_key.strip():
        try:
            client = genai.Client(api_key=api_key)
            st.session_state.gemini_model = client
            st.session_state.api_key_configured = True
            return True
        except Exception as e:
            st.error(f"Error configuring Gemini API: {e}")
            st.session_state.api_key_configured = False
            return False
    else:
        st.warning("Please enter a valid Gemini API key in the sidebar.")
        st.session_state.api_key_configured = False
        return False

# File uploader
uploaded_file = st.file_uploader("Upload a PDF document", type=['pdf'])

# Process uploaded file
if uploaded_file is not None:
    if st.session_state.file_name != uploaded_file.name:
        st.session_state.file_name = uploaded_file.name
        # Clear chat history when new file is uploaded
        st.session_state.chat_history = []

        with st.spinner("Extracting text from PDF..."):
            # Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_path = tmp_file.name

            # Extract text from the temporary file
            try:
                st.session_state.pdf_text = extract_text_from_pdf(tmp_path)

                # Check if extracted text is empty or very short
                if len(st.session_state.pdf_text.strip()) == 0:
                    st.warning("No text found in PDF. Attempting OCR...")

                    # Reset file pointer for OCR
                    uploaded_file.seek(0)

                    # Perform OCR
                    with st.spinner("Performing OCR on PDF... This may take a few moments."):
                        ocr_text = perform_ocr_on_pdf(uploaded_file)

                        if ocr_text.strip():
                            st.session_state.pdf_text = ocr_text
                            st.success("Text was extracted using OCR since the PDF contained images or scanned content.")
                        else:
                            st.error("OCR failed to extract any text from the PDF.")
                else:
                    st.success(f"Text extracted from {uploaded_file.name} successfully!")

                # Show a sample of the extracted text
                if st.session_state.pdf_text.strip():
                    with st.expander("Preview extracted text"):
                        preview_text = st.session_state.pdf_text[:2000] + "..." if len(st.session_state.pdf_text) > 2000 else st.session_state.pdf_text
                        st.text(preview_text)
                        st.info(f"Total characters extracted: {len(st.session_state.pdf_text)}")

            except Exception as e:
                st.error(f"Error processing PDF: {e}")

            # Clean up the temporary file
            try:
                os.unlink(tmp_path)
            except:
                pass

# Configure Gemini API if needed
if api_key and not st.session_state.api_key_configured:
    configure_gemini_api()

# Q&A Section
if st.session_state.pdf_text:
    st.header("Ask questions about your PDF")
    
    # Display chat history
    if st.session_state.chat_history:
        display_chat_history()
        st.markdown("---")
    
    # Use a form to handle input and automatic clearing
    with st.form("question_form", clear_on_submit=True):
        user_question = st.text_input("Enter your question:")
        submit_button = st.form_submit_button("Ask Question")
        
        if submit_button and user_question.strip():
            if not st.session_state.api_key_configured:
                if not configure_gemini_api():
                    st.stop()

            with st.spinner("Generating answer..."):
                try:
                    # Create a prompt that includes the PDF text and the user's question
                    prompt = f"""
                    Here is the text extracted from a tender document:

                    {st.session_state.pdf_text}

                    Based on the above content, please answer the following question:
                    {user_question}.

                    If the reply you want to give consists of a csv, please format it with ```csv and ``` at the start and end of the csv content.

                    If the information to answer the question is not present in the text, please state that clearly.
                    """

                    # Send the prompt to Gemini API
                    response = st.session_state.gemini_model.models.generate_content(
                        model="gemini-2.0-flash", 
                        contents=prompt
                    )

                    # Add to chat history
                    add_to_chat_history(user_question, response.text)

                    # Rerun to refresh the display
                    st.rerun()

                except Exception as e:
                    st.error(f"Error querying Gemini API: {e}")
                    st.error("Please check your API key and try again.")

else:
    if uploaded_file is None:
        st.info("Please upload a PDF file to get started.")
    else:
        st.warning("No text could be extracted from the uploaded PDF.")

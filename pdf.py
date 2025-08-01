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

# Configure tesseract for Streamlit Cloud
if os.path.exists('/usr/bin/tesseract'):
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
elif os.path.exists('/app/.apt/usr/bin/tesseract'):
    pytesseract.pytesseract.tesseract_cmd = '/app/.apt/usr/bin/tesseract'

# Set page configuration
st.set_page_config(page_title="PDF Tender", layout="wide")

# Authentication functions
# def hash_password(password):
#     """Hash password using SHA256"""
#     return hashlib.sha256(str.encode(password)).hexdigest()

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
    st.title("Ruthwik's Document Analyser - Login")
    
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
    st.rerun()

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
# Add logout button in sidebar
# with st.sidebar:
st.write(f"Welcome, {st.session_state.username}!")
if st.button("Logout"):
    logout()

# App title and description
st.title("Ruthwik's Document Analyser")

# Initialize session state variables if they don't exist
if 'pdf_text' not in st.session_state:
    st.session_state.pdf_text = ""
if 'file_name' not in st.session_state:
    st.session_state.file_name = ""
if 'gemini_model' not in st.session_state:
    st.session_state.gemini_model = None
if 'api_key_configured' not in st.session_state:
    st.session_state.api_key_configured = False

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
    user_question = st.text_input("Enter your question:")

    if user_question:
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
                {user_question}

                If the information to answer the question is not present in the text, please state that clearly.
                """

                # Send the prompt to Gemini API
                response = st.session_state.gemini_model.models.generate_content(
                    model="gemini-2.0-flash", 
                    contents=prompt
                )

                # Display the response
                st.subheader("Answer:")
                st.markdown(response.text)

            except Exception as e:
                st.error(f"Error querying Gemini API: {e}")
                st.error("Please check your API key and try again.")
else:
    if uploaded_file is None:
        st.info("Please upload a PDF file to get started.")
    else:
        st.warning("No text could be extracted from the uploaded PDF.")

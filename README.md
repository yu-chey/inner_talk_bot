# 🤖 Inner Talk Bot: AI Psychologist for Telegram

## 🌟 Project Overview

**Inner Talk Bot** is an empathetic, high-performance Telegram application designed to serve as a **first line of accessible psychological support**. Built on Python using the **aiogram** framework and the **Google Gemini** model, it offers anonymous, context-aware assistance. The bot strictly adheres to a therapeutic system prompt, providing practical CBT-based advice and emotional support while storing chat history securely in **MongoDB Atlas** for consistent, long-term dialogue continuity.

### ✨ Key Features

| Feature | Description |
| :--- | :--- |
| **Strict Persona** | The bot strictly follows its system prompt, acting as a supporting AI specialist, and is **forbidden** from redirecting users to external professionals. |
| **Deep Context** | Maintains chat history up to **30 messages** to ensure sequence and relevance during therapeutic interaction. |
| **Asynchronous Core** | Built on `aiogram` and `motor` for maximum performance and responsiveness. |
| **Data Persistence** | Uses **MongoDB Atlas** for reliable storage of chat history. |
| **Reset Command** | The `/clear` command allows users to instantly reset and start a new session. |

---

## 🛠️ Installation and Setup

### 1. 📂 Project Structure

inner_talk_bot/ ├── .venv/ # Virtual Environment 
                ├── .env # Environment Variables File (MUST BE IN .gitignore!) 
                └── bot_service/ # Core Application Package ├── config.py # Constants and .env loading 
                                                            ├── db_manager.py # MongoDB CRUD operations 
                                                            ├── handlers.py # Message and command handlers 
                                                            └── main.py # Entry point and application launch


### 2. 🚀 Get Started

1.  **Clone** the repository and navigate to the project folder:
    ```bash
    git clone [YOUR REPOSITORY LINK]
    cd inner_talk_bot
    ```

2.  **Create and activate** the virtual environment:
    ```bash
    python -m venv .venv
    ```

    For Linux/macOS:
    ```bash
    source .venv/bin/activate
    ```

    For Windows:
    ```bash
    .venv\Scripts\activate
    ```

4.  **Install** dependencies:
    ```bash
    (.venv) pip install aiogram motor google-genai python-dotenv
    ```

### 3. 🔑 Environment Configuration (`.env`)

Create a file named **`.env`** in the project's root folder. **Ensure this file is ignored by Git!**

# --- Telegram and Gemini API Credentials ---
```env
TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

# --- MongoDB Atlas Connection ---
```env
# Verify your login, password, and IP access in MongoDB Atlas.
MONGODB_URI="mongodb+srv://[LOGIN]:[PASSWORD]@[CLUSTER_URI]/[DB_NAME]?retryWrites=true&w=majority"
DB_NAME="innertalkCluster"
```

# --- Bot's System Prompt (Persona Definition) ---
```env
SYSTEM_PROMPT_TEMPLATE="[Paste your complete, carefully refined system prompt text here]"
```

▶️ Running the Application

With your virtual environment active, launch the bot module:
```env

(.venv) python -m bot_service.main

```

The console will display confirmation of the MongoDB connection and that the bot is ready for polling.

## 🛑 Troubleshooting

| Issue | Likely Cause | Solution |
| :--- | :--- | :--- |
| **"ModuleNotFoundError"** | Virtual environment is inactive / packages not installed. | Activate environment (`source .venv/bin/activate`) and run `pip install`. |
| **Bot replies "I am a Google LLM"** | **System prompt is not delivered** (error in `db_manager.py` or `handlers.py`). | **Verify:** 1) `db_manager.py` uses `.sort("timestamp", -1)`. 2) `handlers.py` uses the **message counter logic** for context. |
| **Mongo connection error** | Incorrect URI, password, or IP not in Atlas access list. | Check URI in `.env` and add your IP address to MongoDB Atlas Network Access. |
| **"Critical error: SSL..."** | Certificate conflict (VPN, proxy). | Disable VPN/Proxy or update certificates (`pip install --upgrade certifi`). |

👨‍💻 Developers
```
    yu chey
```

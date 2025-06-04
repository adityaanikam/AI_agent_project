# FlowBit - Multi-Agent AI Processing System

A sophisticated multi-agent AI system built with Python, FastAPI, and LangChain (Gemini) for processing various input formats and triggering appropriate actions.

## Features

- Multi-format input processing (Email, JSON, PDF)
- Intelligent classification of input format and business intent
- Specialized agents for different input types
- Shared memory system for tracking processing history
- Action routing system for follow-up tasks
- Built with Google's Gemini AI model

## Architecture

The system consists of several key components:

1. **Classifier Agent**: Determines input format and business intent
2. **Specialized Agents**:
   - Email Agent: Processes email content, extracts metadata
   - JSON Agent: Validates and processes JSON data
   - PDF Agent: Extracts and analyzes PDF content
3. **Shared Memory**: Stores processing history and agent outputs
4. **Action Router**: Manages follow-up actions based on agent outputs

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your Google API key
```

3. Run the application:
```bash
uvicorn main:app --reload
```

## API Endpoints

- `POST /process`: Upload and process any supported file format
- `GET /status/{process_id}`: Check processing status
- `GET /history`: View processing history

## Development

The project follows a modular architecture:

```
project_flowbit/
├── app/
│   ├── agents/      # Specialized processing agents
│   ├── core/        # Core functionality
│   └── schemas/     # Data models and validation
└── main.py         # FastAPI application entry point
```

## License

MIT 
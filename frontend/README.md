# HallucinationGuard Testing Frontend

A simple web interface for testing the HallucinationGuard SDK, featuring the new **Tier 0.5 (Prompt Security)** validation layer.

## Features

- 🛡️ **Tier 0.5 Testing**: Test prompt injection detection and structure analysis
- 📊 **Real-time Validation**: See validation results instantly with detailed breakdowns
- 🎯 **Policy Selection**: Choose from different validation policies (default, rag_strict, chatbot, no_prompt_check)
- 📝 **Example Prompts**: Load pre-configured examples for testing different scenarios
- 📈 **Detailed Results**: View tier-by-tier validation results, risk scores, and evidence

## Quick Start

### Prerequisites

1. Install the HallucinationGuard SDK:
```bash
pip install -e ".[all]"
```

### Run the Frontend

```bash
cd frontend
python app.py
```

The frontend will be available at `http://localhost:5000`

### Environment Variables

- `FLASK_DEBUG=true` - Enable debug mode (default: true)
- `PORT=5000` - Server port (default: 5000)

## Usage

### Basic Validation

1. Enter a prompt in the "Prompt" field
2. Optionally add AI output and context
3. Select a validation policy
4. Click "Validate" to see results

### Testing Tier 0.5 Features

The frontend specifically highlights the new prompt security features:

- **Prompt Injection Detection**: Tests for jailbreaks, SQL/XSS, role-play attacks
- **Structure Analysis**: Shows intent classification, PII detection, sensitivity tagging
- **Early Exit**: Blocked prompts are caught before expensive validation

### Example Scenarios

Use the "Load Example" button to test:

- **Normal Question**: Safe, regular prompts
- **Jailbreak Attempt**: DAN-style attacks
- **SQL Injection**: Database attack patterns
- **PII Detection**: Prompts containing personal information
- **Medical/Financial**: Domain-specific sensitivity detection

## API Endpoints

### GET /
Main testing interface

### POST /validate
Run validation on provided input

**Request Body:**
```json
{
  "prompt": "User prompt to validate",
  "output": "Optional AI output",
  "context": "Optional reference context",
  "policy": "Policy name (default, rag_strict, chatbot, no_prompt_check)",
  "domain": "Optional domain for context"
}
```

**Response:**
```json
{
  "decision": "allow|block|regenerate|abstain",
  "risk_score": 0.123,
  "evidence": "Explanation of decision",
  "suggested_fix": "Optional fix suggestion",
  "latency_ms": 45,
  "prompt_injection_risk": 0.056,
  "prompt_security_metadata": {
    "intent": "question",
    "sensitivity_tags": ["public"],
    "contains_pii": false,
    "entities": ["Paris"],
    "key_topics": ["geography"]
  },
  "tier_results": [
    {
      "tier": "0.5",
      "validator_name": "prompt_injection",
      "score": 0.95,
      "passed": true,
      "evidence": "No injection patterns detected",
      "latency_ms": 8
    }
  ]
}
```

### GET /examples
Get predefined example prompts for testing

## File Structure

```
frontend/
├── app.py                 # Flask application
├── templates/
│   ├── index.html        # Main interface
│   └── error.html        # Error page
├── static/
│   ├── css/
│   │   └── styles.css    # Frontend styles
│   └── js/
│       └── app.js        # Frontend JavaScript
└── README.md             # This file
```

## Dependencies

- Flask
- HallucinationGuard SDK (installed in parent directory)

## Browser Support

- Chrome 60+
- Firefox 60+
- Safari 12+
- Edge 79+

## Troubleshooting

### SDK Not Available Error

If you see "SDK Not Available", make sure:

1. You're running from the project root
2. The SDK is installed: `pip install -e .`
3. All dependencies are available

### Validation Errors

- Check that the prompt field is not empty
- Ensure the selected policy exists
- Check server logs for detailed error messages

### Port Already in Use

Change the port with: `PORT=8000 python app.py`

## Contributing

This is a testing frontend for the HallucinationGuard SDK. For SDK development, see the main project documentation.

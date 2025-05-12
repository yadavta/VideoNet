# Prompts

This directory contains prompts used across different modules in the VideoNet benchmark system.

## Structure

The prompts directory is organized by task domain:

```
prompts/
│
├── base.py              # Base classes and utilities
├── __init__.py          # Package exports
├── README.md            # This file
│
├── action_recognition/  # Prompts for action recognition tasks
│   ├── __init__.py
│   ├── example.yaml     # Example YAML prompt format
│   │
│   └── negatives/       # Prompts for generating negative examples
│       ├── __init__.py
│       ├── hard_negatives_gpt4_5_o4_refinement.py
│       ├── hard_negatives_gpt4_5_o4_refinement.yaml
│       ├── random_negatives_gpt4_5_o4_refinement.py
│       └── random_negatives_gpt4_5_o4_refinement.yaml
│
└── other_domain/        # Add more task domains as needed
    └── ...
```

## Usage

### From Python Code

```python
from benchmark.prompts import get_prompt, list_prompts, list_categories

# Get all available prompt categories
categories = list_categories()

# List all prompts in a specific category
prompts = list_prompts("action_recognition")

# Get a specific prompt by name
prompt = get_prompt("hard_negatives_gpt4_5_o4_refinement")

# Generate with action list and definition
action = "football"
action_list = [...] # List of actions
action_definition = [...] # List of action definitions
sys_prompt, user_prompts = prompt.get_prompt_data(action, action_list, action_definition)

# Access API parameters from user prompts
api_params = user_prompts[0].api_params
```

### From Command Line

To list all prompt categories:

```bash
python -m benchmark.action_recognition.create_negatives.gpt --list_categories
```

To list prompts in a specific category:

```bash
python -m benchmark.action_recognition.create_negatives.gpt --list_prompts --category action_recognition
```

To list all available prompts:

```bash
python -m benchmark.action_recognition.create_negatives.gpt --list_prompts
```

To generate hard negatives using a prompt:

```bash
python -m benchmark.action_recognition.create_negatives.gpt \
  --prompt hard_negatives_gpt4_5_o4_refinement \
  --action football \
  --action_list benchmark/data/action_lists/football.txt \
  --action_definition benchmark/data/action_definitions/football.txt \
  --output_file benchmark/output/action_recognition/hard_negatives_gpt4_5_o4_refinement/football.json
```

## Creating New Prompts

### YAML Format (Recommended)

For most prompts, use YAML format:

```yaml
system_prompt: >
  Your system prompt here.

user_prompts:
  - content: |
      Your prompt content here.
      You can include placeholders like {ACTION}, {ACTION_LIST}, and {ACTION_DEFINITION}.
    api:
      model: gpt-4o
      temperature: 0.7
      max_tokens: 2048
  
  # Add additional prompt steps as needed
  - content: |
      A follow-up prompt that can refer to previous steps.
    api:
      model: gpt-4o
      temperature: 0.5
      max_tokens: 1024
```

Save the file with a `.yaml` extension in the appropriate subdirectory.

### Python Format

For more complex prompts with custom logic, use Python:

```python
from benchmark.prompts.base import ActionPrompt

# Define your prompt class
class CustomHardNegativesPrompt(ActionPrompt):
    def __init__(self):
        # System prompt 
        sys_prompt = """Your system prompt here"""

        # Multi-step user prompts with API configurations
        user_prompts = [
            {
                "content": """Your prompt content here.
                You can include placeholders like {ACTION}, {ACTION_LIST}, and {ACTION_DEFINITION}.
                """,
                "api": {
                    "model": "gpt-4o",
                    "temperature": 0.7,
                    "max_tokens": 2048,
                }
            },
            # Add more prompt steps as needed
        ]
        
        super().__init__(sys_prompt, user_prompts)
    
    # You can override methods for custom behavior if needed
    def get_prompt_data(self, action, action_list, action_definition):
        # Custom preprocessing logic here
        return super().get_prompt_data(action, action_list, action_definition)

# Create and export the prompt instance
PROMPT = CustomHardNegativesPrompt()
```

## Registration

After creating a new prompt file, register it in `base.py`:

1. Add to `PROMPT_FILES` dictionary with path:
```python
PROMPT_FILES = {
    # Existing prompts...
    "your_new_prompt": PROMPTS_DIR / "action_recognition/negatives/your_new_prompt.yaml",
}
```

2. Add to appropriate category in `PROMPT_CATEGORIES`:
```python
PROMPT_CATEGORIES = {
    "action_recognition": [
        # Existing prompts...
        "your_new_prompt",
    ],
}
```

## Organization Principles

1. **Domain-based organization**: Place prompts in directories that correspond to their domain/task
2. **Descriptive names**: Use descriptive filenames that indicate the purpose and model
3. **Multi-step workflow**: Design prompts with multiple steps for refinement when appropriate
4. **Consistent formatting**: Follow the established format for prompt definitions
5. **Placeholder consistency**: Use {ACTION}, {ACTION_LIST}, and {ACTION_DEFINITION} placeholders
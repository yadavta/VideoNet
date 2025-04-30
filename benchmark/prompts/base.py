from copy import deepcopy
from typing import Dict, List, Any, Optional, Tuple
import regex
import os
import json
import yaml
from pathlib import Path

from dataclasses import dataclass

@dataclass
class UserPrompt:
    """
    Represents a single user prompt with content and optional API parameters.
    """
    content: str
    api_params: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.api_params is None:
            self.api_params = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        result = {"content": self.content}
        if self.api_params:
            result["api"] = self.api_params
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserPrompt':
        """Create from dictionary representation"""
        content = data.get("content", "")
        api_params = data.get("api", {})
        return cls(content=content, api_params=api_params)

# Check if string has unparsed variables, indicated by curly braces
def check_unparsed_variables(string: str) -> bool:
    """
    Check if a string contains unparsed variables.
    
    Args:
        string: The string to check.
        
    Returns:
        True if unparsed variables are found, False otherwise.
    """

    # use regex to check for unparsed variables
    # unparsed variables are indicated by curly braces
    # e.g. {action}, {action_list}, {action_definition}
    pattern = r"\{[a-zA-Z0-9_]+\}"
    matches = regex.findall(pattern, string)

    # print out the matches
    if matches:
        print(f"Unparsed variables found: {matches}")
    return len(matches) > 0

def validate_user_prompts(user_prompts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate that user prompts conform to the expected structure.
    
    Args:
        user_prompts: List of user prompt dictionaries to validate
        
    Returns:
        The validated list of user prompts
        
    Raises:
        ValueError: If any prompt doesn't match the expected format
    """
    validated_prompts = []
    for i, prompt in enumerate(user_prompts):
        try:
            if not isinstance(prompt, dict):
                raise ValueError(f"User prompt at index {i} must be a dictionary, got {type(prompt)}")
            
            # Try converting to UserPrompt dataclass to validate structure
            user_prompt = UserPrompt(
                content=prompt.get("content"),
                api_params=prompt.get("api")
            )
            
            # Convert back to dictionary format for consistency
            validated_prompts.append(user_prompt.to_dict())
        except Exception as e:
            raise ValueError(f"Invalid user prompt at index {i}: {e}")
    
    return validated_prompts

class Prompt:
    """
    Base class for prompts
    """
    def __init__(self, sys_prompt: str, user_prompts: List[Dict[str, Any]]):
        """
        Initialize a prompt object.
        
        Args:
            sys_prompt: System-level prompt defining assistant behavior.
            user_prompts: List of user prompts, each with content and API parameters.
                Each prompt should be a dictionary with at least a 'content' key.
                Optionally, each prompt can include an 'api' key with model parameters.
        """

        self.sys_prompt = sys_prompt
        validate_user_prompts(user_prompts)
        self.user_prompts = user_prompts

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Prompt':
        """
        Create a prompt from a dictionary representation.
        
        Args:
            data: Dictionary with prompt data.
            
        Returns:
            A new Prompt instance.
        """
        sys_prompt = data.get("system_prompt", "")
        user_prompts = data.get("user_prompts", [])
        return cls(sys_prompt, user_prompts)
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'Prompt':
        """
        Load a prompt from a YAML file.
        
        Args:
            yaml_path: Path to YAML file.
            
        Returns:
            A new Prompt instance.
        """
        try:
            with open(yaml_path, 'r') as f:
                data = yaml.safe_load(f)
            return cls.from_dict(data)
        except Exception as e:
            raise ValueError(f"Error loading prompt from {yaml_path}: {e}")
    
    @classmethod
    def from_json(cls, json_path: str) -> 'Prompt':
        """
        Load a prompt from a JSON file.
        
        Args:
            json_path: Path to JSON file.
            
        Returns:
            A new Prompt instance.
        """
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            raise ValueError(f"Error loading prompt from {json_path}: {e}")
    
    def get_prompt_data(self) -> Tuple[str, List[UserPrompt]]:
        """
        Get the list of user prompts.
        
        Returns:
            List of user prompts.
        """

        user_prompts = [UserPrompt.from_dict(user_prompt) for user_prompt in user_prompts]
        return self.sys_prompt, user_prompts


class ActionPrompt(Prompt):
    """
    Extended prompt class specifically for action recognition tasks
    """
    def __init__(self, sys_prompt: str, user_prompts: List[Dict[str, Any]]):
        """
        Initialize an action prompt object.
        
        Args:
            sys_prompt: System-level prompt defining assistant behavior.
            user_prompts: List of user prompts with content and API parameters.
        """
        super().__init__(sys_prompt, user_prompts)
    
    def get_prompt_data(self, action: str, action_list: List[str], action_definition: List[str]=None) -> Tuple[str, List[UserPrompt]]:
        """
        Get the list of user prompts.
        
        Returns:
            List of user prompts.
        """
        if action_definition is None:
            print("Warning: action_definition is None, using empty string")
            action_definition = ""
        
        user_prompts = []
        for user_prompt in self.user_prompts:
            content = user_prompt["content"]
            content = content.format(**{
                "ACTION": action,
                "ACTION_LIST": '\n'.join(action_list),
                "ACTION_DEFINITION": '\n'.join(action_definition),
            })
            check_unparsed_variables(content) # check for unparsed variables
            user_prompt["content"] = content
            user_prompts.append(user_prompt)
        
        user_prompts = [UserPrompt.from_dict(user_prompt) for user_prompt in user_prompts]
        return self.sys_prompt, user_prompts


# Base directory for prompt files
PROMPTS_DIR = Path(__file__).parent

# Dictionary mapping prompt names to YAML/JSON file paths
# Use relative paths from the prompts directory
PROMPT_FILES = {
    # Action Recognition - Hard Negatives
    "hard_negatives_gpt4_5_o4_refinement": PROMPTS_DIR / "action_recognition/negatives/hard_negatives_gpt4_5_o4_refinement.yaml",
    "random_negatives_gpt4_5_o4_refinement": PROMPTS_DIR / "action_recognition/negatives/random_negatives_gpt4_5_o4_refinement.yaml",
    
    # Add more prompts here as they are created
}

# Dictionary mapping categories to prompt names
PROMPT_CATEGORIES = {
    "action_recognition": [
        "hard_negatives_gpt4_5_o4_refinement",
        "random_negatives_gpt4_5_o4_refinement",
    ],
    # Add more categories as needed
}


def get_prompt(prompt_name: str) -> Prompt:
    """
    Get a prompt by name.
    
    Args:
        prompt_name: Name of the prompt to get.
        
    Returns:
        The prompt object.
        
    Raises:
        ValueError: If the prompt is not found.
    """
    if prompt_name not in PROMPT_FILES:
        raise ValueError(f"Prompt '{prompt_name}' not found. Available prompts: {list(PROMPT_FILES.keys())}")
    
    prompt_path = PROMPT_FILES[prompt_name]
    
    # Determine the file type and load appropriately
    if str(prompt_path).endswith(('.yaml', '.yml')):
        # For action recognition prompts, use ActionPrompt
        if any(prompt_name in prompts for cat, prompts in PROMPT_CATEGORIES.items() 
               if cat == "action_recognition"):
            return ActionPrompt.from_yaml(prompt_path)
        return Prompt.from_yaml(prompt_path)
    
    elif str(prompt_path).endswith('.json'):
        # For action recognition prompts, use ActionPrompt
        if any(prompt_name in prompts for cat, prompts in PROMPT_CATEGORIES.items() 
               if cat == "action_recognition"):
            return ActionPrompt.from_json(prompt_path)
        return Prompt.from_json(prompt_path)
    
    else:
        raise ValueError(f"Unsupported prompt file format: {prompt_path}")


def list_prompts(category: Optional[str] = None) -> List[str]:
    """
    List all available prompts, optionally filtered by category.
    
    Args:
        category: Optional category to filter by.
        
    Returns:
        List of prompt names.
    """
    if category:
        return PROMPT_CATEGORIES.get(category, [])
    else:
        return list(PROMPT_FILES.keys())


def list_categories() -> List[str]:
    """
    List all available prompt categories.
    
    Returns:
        List of category names.
    """
    return list(PROMPT_CATEGORIES.keys())
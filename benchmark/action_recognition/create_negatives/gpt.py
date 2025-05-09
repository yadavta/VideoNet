import argparse
import json
import os
import sys
import warnings
from typing import List, Dict, Optional, Any
from loguru import logger

from benchmark.prompts import ActionPrompt, get_prompt, list_prompts, list_categories
from src.utils.openai_api import OpenaiAPI

def load_text_file(file_path) -> list:
    """
    Load a file and return its content.
    
    Args:
        file_path: Path to the file to load.
        
    Returns:
        The content of the file.
    """
    with open(file_path, 'r') as f:
        content = f.read().splitlines()
        content = [line.strip() for line in content if line.strip()]
    return content


def generate_hard_negatives(
    api: OpenaiAPI, 
    action: list[str],
    action_list: List[str], 
    action_definition: List[str], 
    prompt_name: str,
    save_path: Optional[str] = None,
    model_overrides: Optional[Dict[str, Any]] = None,
) -> Dict:
    """
    Generate hard negatives using the OpenAI API.
    
    Args:
        api: OpenAI API instance.
        action_list: List of actions.
        action_definition: List of action definitions.
        prompt_name: Name of the prompt to use for generating hard negatives.
        save_path: Path to save the generated results.
        model_overrides: Optional dictionary to override model parameters in prompts.
        
    Returns:
        The generated hard negatives.
    """
    # Get prompt from registry
    prompt: ActionPrompt = get_prompt(prompt_name)
    
    # Get base system prompt from prompt object
    sys_prompt, user_prompts =  prompt.get_prompt_data(action, action_list, action_definition)
    
    messages = []
    responses = []

    logger.debug(f"System Prompt:\n{sys_prompt}")
    
    # Process user prompts sequentially
    for i, usr_prompt_obj in enumerate(user_prompts):
        # Extract content and API parameters from the prompt object

        usr_prompt_content = usr_prompt_obj.content
        api_params = usr_prompt_obj.api_params
        
        # Override API parameters if specified
        if model_overrides:
            api_params.update(model_overrides)

        logger.debug(f"User Prompt:\n{usr_prompt_content}")
        logger.info(f"Running step {i+1}/{len(user_prompts)} with parameters: {api_params}")

        response, usage = api.call_chatgpt(
            sys_prompt=sys_prompt,
            usr_prompt=usr_prompt_content,
            examples=messages,
            **api_params,
        )

        logger.debug(f"Response:\n{response}")
        logger.debug(f"Usage: {usage}")
        
        # Store metadata about this step
        responses.append({
            "response": response,
            "usage": usage.model_dump() if hasattr(usage, "model_dump") else usage,
            **api_params,
        })

        # Append the system prompt and user prompt to the messages
        messages.append({
            "role": "user",
            "content": usr_prompt_content,
        })
        messages.append({
            "role": "assistant",
            "content": response,
        })
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    # Save results if path provided
    if save_path:
        with open(save_path, 'w') as f:
            json.dump(responses, f, indent=2)
    
    return responses


if __name__ == '__main__':
    """
    python -m benchmark.action_recognition.create_negatives.gpt \
        --prompt random_negatives_gpt4_5_o4_refinement \
        --action football \
        --action_list benchmark/data/action_lists/football.txt \
        --action_definition benchmark/data/action_definitions/football.txt \
        --output_file benchmark/output/action_recognition/random_negatives_gpt4_5_o4_refinement/football.json
    """
    parser = argparse.ArgumentParser(description="Create hard negatives from gpt.")
    parser.add_argument('--prompt', type=str, required=True, help='Prompt name to use for generating hard negatives.')
    parser.add_argument('--action', type=str, required=True, help='Type of action.')
    parser.add_argument('--action_list', type=str, required=True, help='Path to the action list file.')
    parser.add_argument('--action_definition', type=str, required=True, help='Path to the action definition file.')
    parser.add_argument('--output_file', type=str, required=True, help='Path to the output file.')

    parser.add_argument('--list_prompts', action='store_true', help='List all available prompts')
    parser.add_argument('--list_categories', action='store_true', help='List all available prompt categories')
    parser.add_argument('--category', type=str, help='Show prompts for specific category')
    parser.add_argument('--debug', action='store_true', help='Set logging level to DEBUG')

    # Not needed but as a placeholder for future use
    parser.add_argument('--model', type=str, help='Override model to use for generation.')
    parser.add_argument('--temperature', type=float, help='Override temperature for generation.')
    parser.add_argument('--max_tokens', type=int, help='Override maximum tokens for generation.')

    args = parser.parse_args()

    if args.debug:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO")
    
    # List available prompt categories if requested
    if args.list_categories:
        categories = list_categories()
        print("Available prompt categories:")
        for category in categories:
            print(f"  - {category}")
        exit(0)
        
    # List available prompts if requested
    if args.list_prompts:
        if args.category:
            available_prompts = list_prompts(args.category)
            print(f"Available prompts in category '{args.category}':")
        else:
            available_prompts = list_prompts()
            print("Available prompts:")
            
        for prompt in available_prompts:
            print(f"  - {prompt}")
        exit(0)

    api = OpenaiAPI()
    
    action_list = load_text_file(args.action_list)
    action_definition = load_text_file(args.action_definition)
    
    # Build override dict from command line arguments
    model_overrides = {}
    if args.model:
        model_overrides["model"] = args.model
    if args.temperature:
        model_overrides["temperature"] = args.temperature
    if args.max_tokens:
        model_overrides["max_tokens"] = args.max_tokens
    
    overrides = model_overrides if model_overrides else None
    
    results = generate_hard_negatives(
        api=api,
        action=args.action,
        action_list=action_list,
        action_definition=action_definition,
        prompt_name=args.prompt,
        save_path=args.output_file,
        model_overrides=overrides
    )
    
    print(f"Generated hard negatives saved to {args.output_file}")

    print("Results:")
    for result in results:
        print(f"  - {result['response']}")
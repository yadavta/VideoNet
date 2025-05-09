# VideoNet Benchmark

This repository contains tools and datasets for benchmarking multimodal models on video action recognition tasks, with a focus on creating challenging evaluation datasets with carefully balanced hard negative examples.

## Structure

- `action_recognition/`: Tools for generating and evaluating action recognition benchmarks
  - `binary/`: Binary classification tasks (is/is not a specific action)
  - `multiple_choice/`: Multiple choice classification tasks (which action is shown)
  - `create_negatives/`: Tools for generating hard negative examples
- `data/`: Domain-specific action lists and definitions
  - `action_lists/`: Lists of actions for each domain
  - `action_definitions/`: Detailed definitions of actions for each domain
- `prompts/`: Registry of prompt templates used for generating benchmarks ([detailed documentation](prompts/README.md))
  - `action_recognition/`: Action recognition specific prompts
    - `negatives/`: Prompts for generating hard negatives

## Adding Custom Negatives

Collaborators can extend the benchmark by adding new prompts for generating negatives:

1. **Create a Prompt Definition**:
   - Create a new file in the appropriate directory (e.g., `prompts/action_recognition/negatives/`)
   - Use either YAML or Python format
   - Follow the structure in `example.yaml` or existing prompts
   - Use the `Prompt` or `ActionPrompt` base class

2. **Register the Prompt**:
   - Add your prompt to the `PROMPT_FILES` dictionary in `prompts/base.py`
   - Add it to the appropriate category in `PROMPT_CATEGORIES`

3. **Generate Negatives**:
   ```bash
   python -m benchmark.action_recognition.create_negatives.gpt \
     --prompt your_prompt_name \
     --action domain_name \
     --action_list benchmark/data/action_lists/domain_name.txt \
     --action_definition benchmark/data/action_definitions/domain_name.txt \
     --output_file benchmark/output/action_recognition/your_prompt_name/domain_name.json
   ```

4. **Generate Negatives for All Actions in Parallel**:
   ```bash
   # Use the parallel execution script to run for all domains
   bash benchmark/action_recognition/create_negatives/gpt_parallel.sh
   ```

5. **Post-processing and Validation**:
   ```bash
   # Extract CSVs from the generated JSON files
   python benchmark.action_recognition.create_negatives.parse_csv.py
   
   # Validate the generated negatives against action lists
   python benchmark.action_recognition.create_negatives.dist_sanity_check.py
   ```

## Prompt System

The benchmark uses a structured prompt system:

- `Prompt`: Base class for all prompts
- `ActionPrompt`: Extended class for action recognition tasks
- Prompts can be defined in YAML or Python files
- Each prompt consists of a system prompt and multiple user prompts
- Each user prompt can have custom API parameters

## Hard Negative Generation

The hard negative generation process:

1. **Action Categorization**: Group actions into broader categories
2. **Initial Generation**: Create potential hard negatives with balanced distribution
3. **Ambiguity Check**: Identify and resolve pairs that could co-occur in videos
4. **Final Balancing**: Ensure each action appears exactly 3 times as a negative

## Available Commands

List available prompts:
```bash
python -m benchmark.action_recognition.create_negatives.gpt --list_prompts
```

List prompt categories:
```bash
python -m benchmark.action_recognition.create_negatives.gpt --list_categories
```

List prompts in a specific category:
```bash
python -m benchmark.action_recognition.create_negatives.gpt --list_prompts --category action_recognition
```

Generate negatives with debug output:
```bash
python -m benchmark.action_recognition.create_negatives.gpt \
  --prompt hard_negatives_gpt4_5_o4_refinement \
  --action football \
  --action_list benchmark/data/action_lists/football.txt \
  --action_definition benchmark/data/action_definitions/football.txt \
  --output_file benchmark/output/action_recognition/hard_negatives_gpt4_5_o4_refinement/football.json \
  --debug
```

## Extending the Benchmark

To add new domains:
1. Create action list in `data/action_lists/`
2. Create action definitions in `data/action_definitions/`
3. Run existing prompt templates or create custom ones

To add new evaluation formats:
1. Create new scripts in `action_recognition/` directory
2. Use the existing negative generation outputs
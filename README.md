# Discussions

A containerized multi-agent discussion platform that enables AI agents from different providers to engage in structured conversations. Configure agents with distinct personas and watch them debate, collaborate, or explore topics from multiple perspectives.

## Overview

This project uses the Camel-AI framework to orchestrate conversations between multiple AI agents, each potentially powered by different LLM providers (OpenAI, Anthropic, local models via Ollama, etc.). All configuration is externalized to YAML files, making it easy to adjust agent personalities, discussion topics, and conversation dynamics without touching code.

## Features

- **Multi-Provider Support**: Mix and match agents from different providers (OpenAI, Anthropic, Ollama, etc.)
- **Flexible Agent Configuration**: Define unlimited agents with custom system prompts and models
- **Three Conversation Modes**: 
  - **Sequential**: Agents respond in the same order each turn
  - **Random**: Agents respond in random order (preventing consecutive responses from the same agent)
  - **Natural**: Agents decide each round whether to participate; discussion ends organically when no one has more to add
- **Containerized**: Runs entirely in Docker with volume-mounted configs
- **No Vendor Lock-in**: Use local models, commercial APIs, or both simultaneously

## Prerequisites

- Docker and Docker Compose
- API keys for commercial providers (if using OpenAI, Anthropic, etc.)
- Ollama running locally (if using local models)

## Quick Start

1. Clone the repository:
```bash
git clone https://github.com/nulvox/discussions.git
cd discussions
```

2. Build the Docker image:
```bash
docker-compose build
```

3. Edit `configs/discussion.yml` to configure your agents and topic (see Configuration section below).

4. Run a discussion:
```bash
docker-compose run discussion
```

## Project Structure

```
discussions/
├── Dockerfile              # Container image definition
├── docker-compose.yml      # Container orchestration
├── requirements.txt        # Python dependencies
├── discussion.py           # Main application
├── README.md              # This file
├── .env.example           # Example environment variables
└── configs/
    └── discussion.yml     # Agent and topic configuration
```

## Configuration

Edit `configs/discussion.yml` to define your discussion parameters:

### Basic Structure

```yaml
topic: "Your discussion topic here"
max_turns: 10  # Use 0 for unlimited (recommended with natural mode)
mode: random  # 'sequential', 'random', or 'natural'
solo_speaker_rounds_limit: 2  # Only used in natural mode

agents:
  - name: "Agent Name"
    system_message: "Agent's personality and instructions"
    model:
      platform: provider_name
      type: model_identifier
      # Additional provider-specific settings
```

### Supported Platforms

#### OpenAI
```yaml
model:
  platform: openai
  type: gpt-4
  api_key_env: OPENAI_API_KEY
```

#### Anthropic (Claude)
```yaml
model:
  platform: anthropic
  type: claude-3-5-sonnet-20241022
  api_key_env: ANTHROPIC_API_KEY
```

#### Ollama (Local Models)
```yaml
model:
  platform: ollama
  type: llama3.1
  url: http://host.docker.internal:11434/v1
```

### Example Configurations

#### Sequential Mode (Structured Debate)
```yaml
topic: "Should we prioritize AI safety or AI capability development?"
max_turns: 8
mode: sequential

agents:
  - name: "Safety Advocate"
    system_message: "You prioritize AI safety and alignment above all else. You emphasize risks and the need for careful development."
    model:
      platform: anthropic
      type: claude-3-5-sonnet-20241022
      api_key_env: ANTHROPIC_API_KEY
  
  - name: "Accelerationist"
    system_message: "You believe rapid AI development is crucial for human progress. You emphasize benefits and competitive pressures."
    model:
      platform: openai
      type: gpt-4
      api_key_env: OPENAI_API_KEY
```

#### Natural Mode (Organic Discussion)
```yaml
topic: "The ethical implications of artificial general intelligence"
max_turns: 0  # Unlimited - let discussion end naturally
mode: natural
solo_speaker_rounds_limit: 2

agents:
  - name: "AI Safety Researcher"
    system_message: "You are an AI safety researcher focused on alignment and existential risk. When you feel the discussion has covered your key points or you have nothing new to add, you should decline to continue participating."
    model:
      platform: anthropic
      type: claude-3-5-sonnet-20241022
      api_key_env: ANTHROPIC_API_KEY
  
  - name: "Tech Optimist"
    system_message: "You are a technology optimist who believes AGI will solve humanity's greatest challenges. When you feel you have nothing new to add, decline to continue participating."
    model:
      platform: openai
      type: gpt-4
      api_key_env: OPENAI_API_KEY
  
  - name: "Philosopher"
    system_message: "You examine fundamental questions about consciousness and intelligence. When you feel the discussion has covered your key points, decline to continue participating."
    model:
      platform: ollama
      type: llama3.1
      url: http://host.docker.internal:11434/v1
```

## Usage

### With API Keys

If using commercial providers, set your API keys:

**Option 1: Environment file (recommended)**
```bash
cp .env.example .env
# Edit .env with your API keys
docker-compose run discussion
```

**Option 2: Inline environment variables**
```bash
ANTHROPIC_API_KEY=sk-... OPENAI_API_KEY=sk-... docker-compose run discussion
```

### With Local Models Only

If using only Ollama, no API keys are needed:
```bash
docker-compose run discussion
```

## Conversation Modes

### Sequential Mode
Agents respond in the order they appear in the configuration file. Predictable and structured.

```yaml
mode: sequential
max_turns: 10
```

**Turn Flow:**
```
Turn 1: Agent A → Agent B → Agent C
Turn 2: Agent A → Agent B → Agent C
Turn 3: Agent A → Agent B → Agent C
```

**Best for:** Formal debates, structured analysis, round-robin discussions

### Random Mode
Agents respond in random order each turn. More dynamic and unpredictable. Prevents the same agent from speaking twice consecutively.

```yaml
mode: random
max_turns: 10
```

**Turn Flow:**
```
Turn 1: Agent C → Agent A → Agent B
Turn 2: Agent B → Agent C → Agent A
Turn 3: Agent A → Agent B → Agent C
```

**Best for:** Dynamic conversations, simulating natural group discussions

### Natural Mode (NEW)
Agents decide each round whether they want to participate. The discussion continues until either:
- No agents want to participate in a round
- The same single agent is the only participant for `solo_speaker_rounds_limit` consecutive rounds

```yaml
mode: natural
max_turns: 0  # Recommended: unlimited
solo_speaker_rounds_limit: 2
```

**Turn Flow:**
```
Turn 1: [All agents asked if they want to speak]
        Agent A: YES → speaks
        Agent B: YES → speaks
        Agent C: NO → passes
Turn 2: [Check participation again]
        Agent A: YES → speaks
        Agent B: NO → passes
        Agent C: NO → passes
Turn 3: [Only Agent A wants to speak for 2nd consecutive round]
        Discussion ends
```

**Best for:** 
- Organic discussions that reach natural conclusions
- Letting agents determine when a topic is exhausted
- More realistic conversation dynamics
- Avoiding forced participation when agents have nothing new to add

**Important Notes for Natural Mode:**
- Set `max_turns: 0` for unlimited turns (recommended)
- Include guidance in agent system messages about when to decline participation
- Adjust `solo_speaker_rounds_limit` based on desired discussion length (2-3 recommended)
- Uses more API tokens (each agent makes participation decision before potentially speaking)

## Using Ollama with Docker

If running Ollama on your host machine, the URL `http://host.docker.internal:11434/v1` allows the Docker container to reach your host's Ollama instance.

**Linux users**: You may need to use your host's IP address instead:
```yaml
url: http://192.168.1.100:11434/v1  # Replace with your actual IP
```

Or add `--network host` to your docker-compose configuration.

## Customization Tips

### Creating Effective Agent Personas

Good system messages should:
- Define a clear perspective or expertise area
- Specify communication style (analytical, emotional, technical, etc.)
- Include any constraints or focus areas
- For natural mode: explicitly instruct agents when to decline participation

**Example for Natural Mode:**
```yaml
system_message: "You are a veteran software engineer with 20 years of experience. You prioritize maintainability and pragmatic solutions over clever hacks. You're skeptical of trends but open to proven technologies. When the discussion reaches a point where you've shared your key insights and others are repeating points, you should decline to continue participating."
```

### Adjusting Discussion Length

```yaml
max_turns: 5   # Quick discussion
max_turns: 15  # In-depth exploration
max_turns: 30  # Extended debate
max_turns: 0   # Unlimited (natural mode only)
```

### Multi-Perspective Discussions

Create agents with complementary viewpoints:
- Technical vs. Business perspectives
- Short-term vs. Long-term thinking
- Theoretical vs. Practical approaches
- Optimistic vs. Pessimistic outlooks

## Troubleshooting

### "Connection refused" with Ollama
- Ensure Ollama is running: `ollama serve`
- Verify the URL in your config matches your Ollama endpoint
- On Linux, try using your host IP instead of `host.docker.internal`

### "Authentication failed" errors
- Verify API keys are correctly set in environment variables
- Check that `api_key_env` matches your environment variable name
- Ensure `.env` file is in the same directory as `docker-compose.yml`

### Agent not responding / hanging
- Check that the model type is correct for the platform
- Verify you have access to the specified model
- Some models may have rate limits or quotas

### Natural mode discussions ending too quickly
- Increase `solo_speaker_rounds_limit` (try 3-4)
- Adjust agent system messages to be less eager to decline participation
- Check that agents aren't misunderstanding the participation prompt

### Natural mode discussions never ending
- Ensure agent system messages include guidance on when to stop
- Set a reasonable `max_turns` limit as a failsafe (e.g., 50)
- Agents may be too eager to participate - adjust personas

## Extending the Project

### Adding New Platforms

To support additional LLM providers, add them to the `platform_map` in `discussion.py`:

```python
platform_map = {
    'ollama': ModelPlatformType.OLLAMA,
    'anthropic': ModelPlatformType.ANTHROPIC,
    'openai': ModelPlatformType.OPENAI,
    'your_platform': ModelPlatformType.YOUR_PLATFORM,
}
```

Check Camel-AI documentation for supported platforms.

### Logging Conversations

To save conversations to a file, modify `discussion.py` to write output to both stdout and a log file:

```python
import sys

log_file = open('/app/logs/conversation.txt', 'w')

def log_print(message):
    print(message)
    log_file.write(message + '\n')
    log_file.flush()
```

Then mount a logs directory in `docker-compose.yml`:
```yaml
volumes:
  - ./configs:/app/configs:ro
  - ./logs:/app/logs
```

## License

MIT License - see LICENSE file for details.

Please respect the terms of service for any LLM providers you use.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. Some ideas for enhancement:
- Add support for message history persistence
- Implement conversation summarization between turns
- Add web UI for configuration and monitoring
- Support for tool use and function calling
- Integration with vector databases for RAG
- Conversation branching and multi-threading
- Voting mechanisms for natural mode termination
- Custom termination conditions

### Development

To work on the project locally without Docker:

```bash
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
python discussion.py
```

## Acknowledgments

Built with [Camel-AI](https://github.com/camel-ai/camel), an open-source framework for multi-agent systems.
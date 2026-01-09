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
- **Interest-Based Turn Order**: In natural mode, agents with higher interest speak first, with tiebreaking by recency
- **Optional Moderator Scoring**: AI moderator scores participants after each round based on argument quality
- **Conversation Logging**: Save full discussions to file for later review
- **Colored Output**: Agent names displayed in color for easy reading (when terminal supports it)
- **External Prompt Files**: Store long agent prompts in separate files for better organization
- **Connection Verification**: Pre-flight checks ensure all endpoints are reachable before starting
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

3. Edit a config file or use the examples (see Configuration section below).

4. Run a discussion:
```bash
# Use default config (example-simple.yml)
docker-compose run --rm discussion

# Use a specific config file
docker-compose run --rm discussion example-natural.yml

# Use custom config
docker-compose run --rm discussion my-config.yml
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
├── configs/               # Configuration files
│   ├── example-simple.yml
│   ├── example-natural.yml
│   └── prompts/           # External prompt files
│       ├── philosopher.txt
│       └── moderator.txt
└── logs/                  # Conversation logs (created when logging enabled)
```

## Configuration

Edit YAML config files in `configs/` to define your discussion parameters:

### Basic Structure

```yaml
topic: "Your discussion topic here"
max_turns: 10  # Use 0 for unlimited (recommended with natural mode)
mode: random  # 'sequential', 'random', or 'natural'
solo_speaker_rounds_limit: 2  # Only used in natural mode

# Optional: Enable conversation logging
logging:
  enabled: true
  path: /app/logs/conversation.txt

# Optional: Enable moderator scoring
moderator:
  enabled: true
  color: bright_yellow
  system_message_file: "prompts/moderator.txt"
  model:
    platform: ollama
    type: llama3.1
    url: http://host.docker.internal:11434/v1
    max_tokens: 4096
    timeout: null  # null = unlimited for local models

agents:
  - name: "Agent Name"
    color: cyan  # Optional
    system_message: "Agent's personality and instructions"
    # OR use external file:
    # system_message_file: "prompts/agent.txt"
    # Optional: Configure rate limiting with exponential backoff
    rate_limit:
      max_retries: 5      # Maximum retry attempts (default: 5)
      initial_delay: 1    # Initial delay in seconds (default: 1)
      max_delay: 60       # Maximum delay in seconds (default: 60)
    model:
      platform: provider_name
      type: model_identifier
      max_tokens: 4096
      timeout: null  # null for unlimited (recommended for local models)
```

### Agent Prompts

**Inline (for short-medium prompts):**
```yaml
system_message: "Short single-line prompt"
```

**Multiline with `|` (preserves formatting):**
```yaml
system_message: |
  You are an expert in philosophy.
  
  Your background:
  - PhD from Oxford
  - 20 years teaching experience
  
  Your style:
  - Ask probing questions
  - Challenge assumptions
```

**External file (for long prompts):**
```yaml
system_message_file: "prompts/my-agent.txt"
```

### Supported Platforms

#### OpenAI
```yaml
model:
  platform: openai
  type: gpt-4
  api_key_env: OPENAI_API_KEY
  max_tokens: 4096
  timeout: 180  # 3 minutes
```

#### Anthropic (Claude)
```yaml
model:
  platform: anthropic
  type: claude-3-5-sonnet-20241022
  api_key_env: ANTHROPIC_API_KEY
  max_tokens: 4096
  timeout: 180
```

#### Ollama (Local Models)
```yaml
model:
  platform: ollama
  type: llama3.1
  url: http://host.docker.internal:11434/v1
  max_tokens: 4096
  timeout: null  # Unlimited - recommended for local models
```

## Usage

### Basic Usage

```bash
# Use default config
docker-compose run --rm discussion

# Use specific config
docker-compose run --rm discussion example-natural.yml

# With API keys (if using .env file)
docker-compose run --rm discussion
```

### With API Keys

**Option 1: Environment file (recommended)**
```bash
cp .env.example .env
# Edit .env with your API keys
docker-compose run --rm discussion
```

**Option 2: Inline environment variables**
```bash
ANTHROPIC_API_KEY=sk-... OPENAI_API_KEY=sk-... docker-compose run --rm discussion
```

### With Local Models Only

If using only Ollama, no API keys are needed. Make sure Ollama is running:
```bash
ollama serve
docker-compose run --rm discussion
```

## Conversation Modes

### Sequential Mode
Agents respond in the order they appear in the configuration file. Predictable and structured.

```yaml
mode: sequential
max_turns: 10
```

**Best for:** Formal debates, structured analysis, round-robin discussions

### Random Mode
Agents respond in random order each turn. More dynamic and unpredictable. Prevents the same agent from speaking twice consecutively.

```yaml
mode: random
max_turns: 10
```

**Best for:** Dynamic conversations, simulating natural group discussions

### Natural Mode
Agents rate their interest (0-10) each round and decide whether to participate. The discussion continues until either:
- No agents want to participate in a round
- The same single agent is the only participant for `solo_speaker_rounds_limit` consecutive rounds

Agents are sorted by interest level (highest first), with tiebreaking by who spoke least recently, then by config order.

```yaml
mode: natural
max_turns: 0  # Recommended: unlimited
solo_speaker_rounds_limit: 2
```

**Best for:** 
- Organic discussions that reach natural conclusions
- Letting agents determine when a topic is exhausted
- More realistic conversation dynamics

## Moderator Scoring

Enable an AI moderator to score participant responses after each round:

```yaml
moderator:
  enabled: true
  color: bright_yellow
  system_message_file: "prompts/moderator.txt"
  model:
    platform: ollama
    type: llama3.1
    url: http://host.docker.internal:11434/v1
```

**Scoring:**
- Range: -5 to +5 per response
- Positive: Strong arguments, evidence, staying on-topic
- Negative: Logical fallacies, personal attacks, going off-topic
- Running totals displayed after each round
- Final scores shown at end of discussion

**Example output:**
```
--- Moderator Scoring ---
  AI Safety Researcher: +3 (total: 15)
  Tech Optimist: +2 (total: 12)
  Philosopher: +4 (total: 18)
```

## Conversation Logging

Enable logging to save full conversations:

```yaml
logging:
  enabled: true
  path: /app/logs/conversation.txt  # Optional, this is default
```

Logs are saved to `./logs/` on your host machine and persist after the container exits.

## Colored Output

Assign colors to agents for easier reading:

```yaml
agents:
  - name: "Safety Advocate"
    color: red
    # or: bright_red, green, bright_green, blue, bright_blue, 
    #     cyan, bright_cyan, magenta, bright_magenta, yellow, bright_yellow
```

Colors only work when terminal supports them (automatically detected).

## Rate Limiting

The application handles API rate limits automatically with exponential backoff. Configure per-agent:

```yaml
agents:
  - name: "Agent Name"
    rate_limit:
      max_retries: 5      # Maximum retry attempts (default: 5)
      initial_delay: 1    # Initial delay in seconds (default: 1)
      max_delay: 60       # Maximum delay in seconds (default: 60)
```

**How it works:**
- Automatically detects rate limit errors (429, "rate limit exceeded", etc.)
- Retries with exponential backoff: 1s, 2s, 4s, 8s, 16s...
- Caps delay at `max_delay` to avoid excessive waiting
- Shows retry messages: "Rate limit hit for Agent Name. Retrying in 4s..."
- Throws error if max retries exceeded

**Default behavior** (if not configured):
- 5 retries with 1s initial delay, 60s max delay
- Suitable for most commercial APIs

**For heavy usage:**
```yaml
rate_limit:
  max_retries: 10
  initial_delay: 2
  max_delay: 120
```

Rate limiting also applies to moderator scoring if enabled.

## Using Ollama with Docker

If running Ollama on your host machine, the URL `http://host.docker.internal:11434/v1` allows the Docker container to reach your host's Ollama instance.

**Linux users**: You may need to use your host's IP address instead:
```yaml
url: http://192.168.1.100:11434/v1  # Replace with your actual IP
```

Or add `network_mode: host` to your docker-compose configuration.

**Important**: Set `timeout: null` for Ollama models to avoid timeouts with slower local models.

## Customization Tips

### Creating Effective Agent Personas

Good system messages should:
- Define a clear perspective or expertise area
- Specify communication style (analytical, emotional, technical, etc.)
- Include any constraints or focus areas
- For natural mode: explicitly instruct agents when to decline participation

**Example:**
```yaml
system_message: |
  You are a veteran software engineer with 20 years of experience.
  
  Your priorities:
  - Maintainability over clever hacks
  - Proven technologies over trends
  - Pragmatic solutions over perfect ones
  
  Your style:
  - Direct and concise
  - Ask clarifying questions
  - Cite real-world examples
  
  When the discussion has covered your key insights, decline to participate.
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
```
Unable to connect to ollama endpoint...
```
- Ensure Ollama is running: `ollama serve`
- Verify the model is available: `ollama list`
- Check the URL in your config matches your Ollama endpoint
- On Linux, try using your host IP instead of `host.docker.internal`

### "Authentication failed" errors
- Verify API keys are correctly set in environment variables
- Check that `api_key_env` matches your environment variable name
- Ensure `.env` file is in the same directory as `docker-compose.yml`

### Agent not responding / hanging
- Check that the model type is correct for the platform
- Verify you have access to the specified model
- For local models: Set `timeout: null` to allow unlimited response time
- Some commercial models may have rate limits or quotas

### Natural mode discussions ending too quickly
- Increase `solo_speaker_rounds_limit` (try 3-4)
- Adjust agent system messages to be less eager to decline participation
- Ensure agents have clear guidance on when to continue vs. stop

### Natural mode discussions never ending
- Set a reasonable `max_turns` limit as a failsafe (e.g., 50)
- Ensure agent system messages include guidance on when to stop
- Agents may be too eager to participate - adjust personas

### Moderator giving inconsistent scores
- Use more specific scoring criteria in the moderator prompt
- Increase `max_tokens` for moderator to allow more reasoning
- Try different models - some follow numerical instructions better

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

## License

MIT License - see LICENSE file for details.

Please respect the terms of service for any LLM providers you use.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. Some ideas for enhancement:
- Support for message history persistence across sessions
- Web UI for configuration and monitoring
- Support for tool use and function calling
- Integration with vector databases for RAG
- Conversation branching and multi-threading
- Voting mechanisms for natural mode termination
- Custom termination conditions
- Real-time streaming of agent responses

### Development

To work on the project locally without Docker:

```bash
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt

# Run with specific config
python discussion.py configs/example-natural.yml
```

## Acknowledgments

Built with [Camel-AI](https://github.com/camel-ai/camel), an open-source framework for multi-agent systems.
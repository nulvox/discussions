#!/usr/bin/env python3
import yaml
import random
import os
import logging
import sys
import time
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.types import ModelPlatformType

# Suppress camel-ai warnings
logging.getLogger('camel').setLevel(logging.ERROR)
logging.getLogger('root').setLevel(logging.ERROR)

# ANSI color codes
COLORS = {
    'black': '\033[30m',
    'red': '\033[31m',
    'green': '\033[32m',
    'yellow': '\033[33m',
    'blue': '\033[34m',
    'magenta': '\033[35m',
    'cyan': '\033[36m',
    'white': '\033[37m',
    'bright_black': '\033[90m',
    'bright_red': '\033[91m',
    'bright_green': '\033[92m',
    'bright_yellow': '\033[93m',
    'bright_blue': '\033[94m',
    'bright_magenta': '\033[95m',
    'bright_cyan': '\033[96m',
    'bright_white': '\033[97m',
    'reset': '\033[0m'
}

def supports_color():
    """
    Check if the terminal supports color output
    """
    # Check if stdout is a TTY
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return False
    
    # Check TERM environment variable
    term = os.environ.get('TERM', '')
    if term == 'dumb':
        return False
    
    # Check for color support indicators
    if 'color' in term or term in ['xterm', 'xterm-256color', 'screen', 'screen-256color', 'linux']:
        return True
    
    # Check COLORTERM
    if os.environ.get('COLORTERM'):
        return True
    
    return False

def colorize(text, color):
    """Apply color to text if colors are supported"""
    if not supports_color():
        return text
    
    color_code = COLORS.get(color.lower(), '')
    reset_code = COLORS['reset']
    
    if color_code:
        return f"{color_code}{text}{reset_code}"
    return text


def call_with_rate_limiting(func, agent_name, rate_limit_config=None):
    """
    Call a function with exponential backoff on rate limit errors
    
    Args:
        func: Function to call (typically agent.step())
        agent_name: Name of the agent (for logging)
        rate_limit_config: Dict with 'max_retries', 'initial_delay', 'max_delay'
    """
    if rate_limit_config is None:
        rate_limit_config = {
            'max_retries': 5,
            'initial_delay': 1,
            'max_delay': 60
        }
    
    max_retries = rate_limit_config.get('max_retries', 5)
    initial_delay = rate_limit_config.get('initial_delay', 1)
    max_delay = rate_limit_config.get('max_delay', 60)
    
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            error_str = str(e).lower()
            
            # Check if it's a rate limit error
            is_rate_limit = any(phrase in error_str for phrase in [
                'rate limit',
                'rate_limit',
                'ratelimit',
                'too many requests',
                '429',
                'quota exceeded',
                'rate exceeded'
            ])
            
            if not is_rate_limit or attempt == max_retries:
                # Not a rate limit error, or we're out of retries
                raise
            
            # Calculate delay with exponential backoff
            delay = min(initial_delay * (2 ** attempt), max_delay)
            
            print(f"Rate limit hit for {agent_name}. Retrying in {delay}s... (attempt {attempt + 1}/{max_retries})", 
                  file=sys.stderr)
            time.sleep(delay)
    
    # Should never reach here, but just in case
    raise Exception(f"Failed after {max_retries} retries")


def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def verify_agent_connection(agent_config):
    """
    Verify that the agent's model endpoint is reachable before starting
    Returns (success: bool, error_message: str or None)
    """
    model_config = agent_config['model']
    platform = model_config['platform']
    agent_name = agent_config['name']
    
    # Only verify endpoints with URLs (Ollama and custom endpoints)
    if 'url' not in model_config:
        return True, None
    
    url = model_config['url']
    
    try:
        import requests
        # Try to reach the endpoint with a short timeout
        # For Ollama, check the /api/tags endpoint
        if platform == 'ollama':
            # Extract base URL (remove /v1 suffix if present)
            base_url = url.replace('/v1', '').rstrip('/')
            test_url = f"{base_url}/api/tags"
            response = requests.get(test_url, timeout=5)
            
            if response.status_code == 200:
                return True, None
            else:
                return False, f"Ollama endpoint returned status {response.status_code}"
        else:
            # For other endpoints, just try a basic connection
            response = requests.get(url, timeout=5)
            return True, None
            
    except requests.exceptions.ConnectionError:
        error_msg = f"""
Unable to connect to {platform} endpoint for agent '{agent_name}'
URL: {url}

Possible causes:
"""
        if platform == 'ollama':
            error_msg += """  - Ollama service is not running
    Start it with: ollama serve
  - Ollama is running on a different port
    Check with: ollama list
  - Docker cannot reach host (try your host IP instead of host.docker.internal)
    Example: http://192.168.1.100:11434/v1
"""
        else:
            error_msg += f"""  - The {platform} service is not running
  - The URL is incorrect
  - Firewall is blocking the connection
"""
        return False, error_msg
        
    except requests.exceptions.Timeout:
        return False, f"Connection to {platform} endpoint timed out for agent '{agent_name}' at {url}"
        
    except Exception as e:
        return False, f"Error connecting to {platform} endpoint for agent '{agent_name}': {str(e)}"


def create_moderator(moderator_config):
    """Create a moderator agent for scoring participants"""
    model_config = moderator_config['model']
    platform_map = {
        'ollama': ModelPlatformType.OLLAMA,
        'anthropic': ModelPlatformType.ANTHROPIC,
        'openai': ModelPlatformType.OPENAI,
    }
    
    platform = platform_map[model_config['platform']]
    
    # Get timeout setting
    if 'timeout' in model_config:
        timeout = model_config['timeout']
    elif model_config['platform'] == 'ollama':
        timeout = None
    else:
        timeout = 180
    
    model_kwargs = {
        'model_platform': platform,
        'model_type': model_config['type'],
        'model_config_dict': {
            'max_tokens': model_config.get('max_tokens', 4096),
            'timeout': timeout if timeout is not None else 999999,
        }
    }
    
    if 'url' in model_config:
        model_kwargs['url'] = model_config['url']
    
    if 'api_key_env' in model_config:
        api_key = os.getenv(model_config['api_key_env'])
        if api_key:
            model_kwargs['api_key'] = api_key
    
    model = ModelFactory.create(**model_kwargs)
    
    # Get system message - either inline or from file
    if 'system_message' in moderator_config:
        system_message = moderator_config['system_message']
    elif 'system_message_file' in moderator_config:
        prompt_path = moderator_config['system_message_file']
        if not prompt_path.startswith('/'):
            prompt_path = f"/app/configs/{prompt_path}"
        with open(prompt_path, 'r') as f:
            system_message = f.read()
    else:
        raise ValueError("Moderator must have either 'system_message' or 'system_message_file'")
    
    return {
        'color': moderator_config.get('color', None),
        'rate_limit': moderator_config.get('rate_limit', {
            'max_retries': 5,
            'initial_delay': 1,
            'max_delay': 60
        }),
        'agent': ChatAgent(
            system_message=system_message,
            model=model,
            step_timeout=timeout
        )
    }


def create_agent(agent_config):
    model_config = agent_config['model']
    platform_map = {
        'ollama': ModelPlatformType.OLLAMA,
        'anthropic': ModelPlatformType.ANTHROPIC,
        'openai': ModelPlatformType.OPENAI,
    }
    
    platform = platform_map[model_config['platform']]
    
    # Get timeout setting (None = unlimited, otherwise seconds)
    # Default to 180s for commercial APIs, None for Ollama
    if 'timeout' in model_config:
        timeout = model_config['timeout']
    elif model_config['platform'] == 'ollama':
        timeout = None  # Unlimited for local models
    else:
        timeout = 180  # 3 minutes for hosted APIs
    
    model_kwargs = {
        'model_platform': platform,
        'model_type': model_config['type'],
        'model_config_dict': {
            'max_tokens': model_config.get('max_tokens', 4096),
            # Set request timeout - for None (unlimited), use a very large number
            'timeout': timeout if timeout is not None else 999999,
        }
    }
    
    if 'url' in model_config:
        model_kwargs['url'] = model_config['url']
    
    if 'api_key_env' in model_config:
        api_key = os.getenv(model_config['api_key_env'])
        if api_key:
            model_kwargs['api_key'] = api_key
    
    model = ModelFactory.create(**model_kwargs)
    
    # Get system message - either inline or from file
    if 'system_message' in agent_config:
        system_message = agent_config['system_message']
    elif 'system_message_file' in agent_config:
        # Load from external file
        prompt_path = agent_config['system_message_file']
        # If relative path, make it relative to /app/configs
        if not prompt_path.startswith('/'):
            prompt_path = f"/app/configs/{prompt_path}"
        with open(prompt_path, 'r') as f:
            system_message = f.read()
    else:
        raise ValueError(f"Agent {agent_config['name']} must have either 'system_message' or 'system_message_file'")
    
    return {
        'name': agent_config['name'],
        'color': agent_config.get('color', None),
        'rate_limit': agent_config.get('rate_limit', {
            'max_retries': 5,
            'initial_delay': 1,
            'max_delay': 60
        }),
        'agent': ChatAgent(
            system_message=system_message,
            model=model,
            step_timeout=timeout
        )
    }

def should_participate(agent_data, messages, is_first_turn=False):
    """Ask agent if they want to participate this round and how interested they are"""
    if is_first_turn:
        decision_content = "Do you want to participate in this discussion? Rate your interest from 0 (not interested, will not participate) to 10 (very interested, have important points to make). Reply with only a number 0-10."
    else:
        decision_content = "Given the discussion so far, how interested are you in contributing further? Rate from 0 (nothing more to add, will not participate) to 10 (very interested, have important points to make). Reply with only a number 0-10."
    
    decision_prompt = BaseMessage.make_user_message(
        role_name="Moderator",
        content=decision_content
    )
    
    try:
        response = call_with_rate_limiting(
            lambda: agent_data['agent'].step(decision_prompt),
            agent_data['name'],
            agent_data.get('rate_limit')
        )
        response_text = response.msg.content.strip()
        
        # Extract number from response
        import re
        numbers = re.findall(r'\d+', response_text)
        if numbers:
            score = int(numbers[0])
            # Clamp to 0-10 range
            score = max(0, min(10, score))
            return score
        else:
            # If can't parse, default to participating with medium interest
            return 5
    except Exception as e:
        print(f"Error getting participation decision from {agent_data['name']}: {e}")
        # Default to medium interest if there's an error
        return 5

def run_discussion(config_path=None):
    if config_path is None:
        config_path = os.getenv('CONFIG_PATH', '/app/configs/example-simple.yml')
    
    config = load_config(config_path)
    
    # Set up conversation logging if enabled
    log_file = None
    if config.get('logging', {}).get('enabled', False):
        log_path = config.get('logging', {}).get('path', '/app/logs/conversation.txt')
        # Create logs directory if it doesn't exist
        log_dir = os.path.dirname(log_path)
        os.makedirs(log_dir, exist_ok=True)
        log_file = open(log_path, 'w', encoding='utf-8')
        
        def log_print(message='', end='\n'):
            """Print to both stdout and log file"""
            print(message, end=end)
            if log_file:
                log_file.write(message + end)
                log_file.flush()
    else:
        def log_print(message='', end='\n'):
            """Print only to stdout"""
            print(message, end=end)
    
    # Verify all agent connections before starting
    log_print("Verifying agent connections...\n")
    for agent_config in config['agents']:
        agent_name = agent_config['name']
        log_print(f"  Checking {agent_name}...", end=' ')
        success, error_msg = verify_agent_connection(agent_config)
        if not success:
            log_print("FAILED")
            log_print(f"\n{error_msg}")
            log_print("\nPlease fix the connection issue and try again.")
            if log_file:
                log_file.close()
            return
        log_print("OK")
    log_print()
    
    # Create all agents
    agents = [create_agent(agent_config) for agent_config in config['agents']]
    
    # Create moderator if enabled
    moderator = None
    agent_scores = {agent['name']: 0 for agent in agents}
    if config.get('moderator', {}).get('enabled', False):
        moderator = create_moderator(config['moderator'])
        log_print("Moderator enabled for scoring\n")
    
    # Initialize conversation
    topic = config['topic']
    max_turns = config.get('max_turns', 10)
    mode = config.get('mode', 'sequential')
    solo_speaker_limit = config.get('solo_speaker_rounds_limit', 2)
    
    initial_message = BaseMessage.make_user_message(
        role_name="Moderator",
        content=f"Discuss: {topic}"
    )
    
    messages = [initial_message]
    log_print(f"\n{'='*80}")
    log_print(f"Topic: {topic}")
    log_print(f"Mode: {mode}")
    log_print(f"Max turns: {'Unlimited' if max_turns == 0 else max_turns}")
    log_print(f"Participants: {', '.join([a['name'] for a in agents])}")
    log_print(f"{'='*80}\n")
    
    last_speaker_idx = None
    solo_rounds = 0
    last_solo_speaker = None
    turn = 0
    
    # Track when each agent last spoke (turn number)
    agent_last_spoke = {agent['name']: 0 for agent in agents}
    
    # Track the full discussion history (without system prompts)
    discussion_history = []
    
    while True:
        turn += 1
        
        # Check turn limit (0 means unlimited)
        if max_turns > 0 and turn > max_turns:
            log_print("\n--- Maximum turns reached ---\n")
            break
        
        log_print(f"\n--- Turn {turn} ---\n")
        
        # Natural mode: ask agents if they want to participate
        if mode == 'natural':
            log_print("Checking participation...\n")
            participation_scores = []
            for agent_data in agents:
                interest_score = should_participate(agent_data, messages, is_first_turn=(turn == 1))
                participation_scores.append((agent_data, interest_score))
                if interest_score > 0:
                    log_print(f"  {agent_data['name']}: interest level {interest_score}/10")
                else:
                    log_print(f"  {agent_data['name']}: passing")
            
            log_print()
            
            # Filter to only agents who want to participate (score > 0)
            participants = [agent_data for agent_data, score in participation_scores if score > 0]
            
            # Sort by:
            # 1. Interest score (descending) - higher interest speaks first
            # 2. Last spoke turn (ascending) - spoke longer ago speaks first in ties
            # 3. Config order (ascending) - earlier in config speaks first as final tiebreaker
            participation_scores = [(agent_data, score) for agent_data, score in participation_scores if score > 0]
            participation_scores.sort(
                key=lambda x: (
                    -x[1],  # Interest score (negative for descending)
                    agent_last_spoke[x[0]['name']],  # Last spoke turn (ascending)
                    agents.index(x[0])  # Config order (ascending)
                )
            )
            participants = [agent_data for agent_data, score in participation_scores]
            
            # Check termination conditions
            if len(participants) == 0:
                log_print("Discussion concluded - no agents wish to continue\n")
                break
            
            # Check if same solo speaker for multiple rounds
            if len(participants) == 1:
                current_solo = participants[0]['name']
                if last_solo_speaker == current_solo:
                    solo_rounds += 1
                    if solo_rounds >= solo_speaker_limit:
                        log_print(f"Discussion concluded - only {current_solo} participated for {solo_speaker_limit} consecutive rounds\n")
                        break
                else:
                    solo_rounds = 1
                    last_solo_speaker = current_solo
            else:
                solo_rounds = 0
                last_solo_speaker = None
            
            agent_order = participants
        
        # Sequential mode: agents in config order
        elif mode == 'sequential':
            agent_order = agents
        
        # Random mode: randomized order, prevent consecutive same speaker
        else:  # random mode
            agent_order = agents.copy()
            random.shuffle(agent_order)
        
        # Have agents speak
        for agent_data in agent_order:
            # In random mode, prevent same agent speaking twice in a row
            if mode == 'random' and last_speaker_idx is not None:
                current_idx = agents.index(agent_data)
                if current_idx == last_speaker_idx:
                    continue
            
            # Build a combined prompt with the full discussion history
            # This includes the topic and all previous responses from all agents
            if len(discussion_history) == 0:
                # First speaker of the discussion
                combined_content = f"Continue the discussion on: {topic}"
            else:
                # Build the context with who said what
                context_parts = [f"Discussion topic: {topic}\n"]
                for hist_speaker, hist_content in discussion_history:
                    context_parts.append(f"\n{hist_speaker}:\n{hist_content}")
                context_parts.append(f"\n\nYour turn to respond:")
                combined_content = "".join(context_parts)
            
            discussion_prompt = BaseMessage.make_user_message(
                role_name="Moderator",
                content=combined_content
            )
            
            # Agent responds with full context but keeps their own system prompt
            response = call_with_rate_limiting(
                lambda: agent_data['agent'].step(discussion_prompt),
                agent_data['name'],
                agent_data.get('rate_limit')
            )
            messages.append(response.msg)
            
            # Add this response to the shared discussion history
            discussion_history.append((agent_data['name'], response.msg.content))
            
            agent_name = agent_data['name']
            agent_color = agent_data.get('color')
            
            if agent_color:
                log_print(f"{colorize(agent_name + ':', agent_color)}")
            else:
                log_print(f"{agent_name}:")
            
            log_print(f"{response.msg.content}\n")
            
            last_speaker_idx = agents.index(agent_data)
            agent_last_spoke[agent_data['name']] = turn  # Track when this agent spoke
        
        # Moderator scoring at end of round
        if moderator:
            log_print("\n--- Moderator Scoring ---\n")
            
            for agent_data in agent_order:
                # Build the scoring prompt with the agent's response
                scoring_prompt = BaseMessage.make_user_message(
                    role_name="Moderator",
                    content=f"""Score the following response from {agent_data['name']} on the topic "{topic}".

Response:
{messages[-len(agent_order) + agent_order.index(agent_data)].content}

Provide a score adjustment between -5 and +5 based on:
- Strong arguments and evidence: positive points
- Going off-topic: negative points
- Logical fallacies: negative points
- Personal attacks on other participants: negative points

Reply with ONLY a number between -5 and +5."""
                )
                
                try:
                    score_response = call_with_rate_limiting(
                        lambda: moderator['agent'].step(scoring_prompt),
                        "Moderator",
                        moderator.get('rate_limit')
                    )
                    score_text = score_response.msg.content.strip()
                    
                    # Extract number from response
                    import re
                    numbers = re.findall(r'-?\d+', score_text)
                    if numbers:
                        score_delta = int(numbers[0])
                        score_delta = max(-5, min(5, score_delta))  # Clamp to -5 to +5
                        agent_scores[agent_data['name']] += score_delta
                        
                        moderator_color = moderator.get('color')
                        score_str = f"{agent_data['name']}: {score_delta:+d} (total: {agent_scores[agent_data['name']]})"
                        
                        if moderator_color:
                            log_print(f"  {colorize(score_str, moderator_color)}")
                        else:
                            log_print(f"  {score_str}")
                except Exception as e:
                    log_print(f"  Error scoring {agent_data['name']}: {e}")
            
            log_print()
    
    log_print(f"{'='*80}")
    log_print(f"Discussion ended after {turn} turns")
    log_print(f"{'='*80}\n")
    
    # Display final scores if moderator was enabled
    if moderator:
        log_print("Final Scores:")
        sorted_scores = sorted(agent_scores.items(), key=lambda x: x[1], reverse=True)
        for agent_name, score in sorted_scores:
            log_print(f"  {agent_name}: {score}")
        log_print()
    
    if log_file:
        log_file.close()
        log_path = config.get('logging', {}).get('path', '/app/logs/conversation.txt')
        print(f"\nConversation logged to: {log_path}")

if __name__ == '__main__':
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Multi-agent discussion platform using Camel-AI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default config
  python discussion.py
  
  # Use specific config file
  python discussion.py example-natural.yml
  python discussion.py /app/configs/my-config.yml
  
  # In Docker
  docker-compose run --rm discussion example-natural.yml
        """
    )
    
    parser.add_argument(
        'config',
        nargs='?',
        default=None,
        help='Path to configuration file (default: from CONFIG_PATH env or example-simple.yml)'
    )
    
    args = parser.parse_args()
    
    config_file = args.config
    if config_file:
        # If it's a relative path without /app/configs prefix, add it
        if not config_file.startswith('/'):
            config_file = f"/app/configs/{config_file}"
    
    run_discussion(config_file)
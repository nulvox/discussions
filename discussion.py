#!/usr/bin/env python3
import yaml
import random
import os
import logging
import sys
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
        'color': agent_config.get('color', None),  # Optional color for this agent
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
        response = agent_data['agent'].step(decision_prompt)
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
    
    # Verify all agent connections before starting
    print("Verifying agent connections...\n")
    for agent_config in config['agents']:
        agent_name = agent_config['name']
        print(f"  Checking {agent_name}...", end=' ')
        success, error_msg = verify_agent_connection(agent_config)
        if not success:
            print("FAILED")
            print(f"\n{error_msg}")
            print("\nPlease fix the connection issue and try again.")
            return
        print("OK")
    print()
    
    # Create all agents
    agents = [create_agent(agent_config) for agent_config in config['agents']]
    
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
    print(f"\n{'='*80}")
    print(f"Topic: {topic}")
    print(f"Mode: {mode}")
    print(f"Max turns: {'Unlimited' if max_turns == 0 else max_turns}")
    print(f"Participants: {', '.join([a['name'] for a in agents])}")
    print(f"{'='*80}\n")
    
    last_speaker_idx = None
    solo_rounds = 0
    last_solo_speaker = None
    turn = 0
    
    # Track when each agent last spoke (turn number)
    agent_last_spoke = {agent['name']: 0 for agent in agents}
    
    while True:
        turn += 1
        
        # Check turn limit (0 means unlimited)
        if max_turns > 0 and turn > max_turns:
            print("\n--- Maximum turns reached ---\n")
            break
        
        print(f"\n--- Turn {turn} ---\n")
        
        # Natural mode: ask agents if they want to participate
        if mode == 'natural':
            print("Checking participation...\n")
            participation_scores = []
            for agent_data in agents:
                interest_score = should_participate(agent_data, messages, is_first_turn=(turn == 1))
                participation_scores.append((agent_data, interest_score))
                if interest_score > 0:
                    print(f"  {agent_data['name']}: interest level {interest_score}/10")
                else:
                    print(f"  {agent_data['name']}: passing")
            
            print()
            
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
                print("Discussion concluded - no agents wish to continue\n")
                break
            
            # Check if same solo speaker for multiple rounds
            if len(participants) == 1:
                current_solo = participants[0]['name']
                if last_solo_speaker == current_solo:
                    solo_rounds += 1
                    if solo_rounds >= solo_speaker_limit:
                        print(f"Discussion concluded - only {current_solo} participated for {solo_speaker_limit} consecutive rounds\n")
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
        # Create a prompt for continuing the discussion
        discussion_prompt = BaseMessage.make_user_message(
            role_name="Moderator",
            content=f"Continue the discussion on: {topic}"
        )
        
        for agent_data in agent_order:
            # In random mode, prevent same agent speaking twice in a row
            if mode == 'random' and last_speaker_idx is not None:
                current_idx = agents.index(agent_data)
                if current_idx == last_speaker_idx:
                    continue
            
            # Agent gets full context including what others said earlier this round
            response = agent_data['agent'].step(discussion_prompt)
            messages.append(response.msg)
            
            agent_name = agent_data['name']
            agent_color = agent_data.get('color')
            
            if agent_color:
                print(f"{colorize(agent_name + ':', agent_color)}")
            else:
                print(f"{agent_name}:")
            
            print(f"{response.msg.content}\n")
            
            last_speaker_idx = agents.index(agent_data)
            agent_last_spoke[agent_data['name']] = turn  # Track when this agent spoke
            
            # After each agent speaks, update ALL other participating agents' context
            # so they can respond to what was just said
            for other_agent_data in agent_order:
                if other_agent_data != agent_data:
                    # Update the other agent's memory with what was just said
                    other_agent_data['agent'].update_memory(response.msg, "assistant")
    
    print(f"{'='*80}")
    print(f"Discussion ended after {turn} turns")
    print(f"{'='*80}\n")

if __name__ == '__main__':
    run_discussion()
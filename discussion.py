#!/usr/bin/env python3
import yaml
import random
import os
import logging
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.types import ModelPlatformType

# Suppress camel-ai warnings
logging.getLogger('camel').setLevel(logging.ERROR)
logging.getLogger('root').setLevel(logging.ERROR)

def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def create_agent(agent_config):
    model_config = agent_config['model']
    platform_map = {
        'ollama': ModelPlatformType.OLLAMA,
        'anthropic': ModelPlatformType.ANTHROPIC,
        'openai': ModelPlatformType.OPENAI,
    }
    
    platform = platform_map[model_config['platform']]
    model_kwargs = {
        'model_platform': platform,
        'model_type': model_config['type'],
        'model_config_dict': {
            'max_tokens': model_config.get('max_tokens', 4096)
        }
    }
    
    if 'url' in model_config:
        model_kwargs['url'] = model_config['url']
    
    if 'api_key_env' in model_config:
        api_key = os.getenv(model_config['api_key_env'])
        if api_key:
            model_kwargs['api_key'] = api_key
    
    model = ModelFactory.create(**model_kwargs)
    
    # Get timeout setting (None = unlimited, otherwise seconds)
    # Default to 180s for commercial APIs, None for Ollama
    if 'timeout' in model_config:
        timeout = model_config['timeout']
    elif model_config['platform'] == 'ollama':
        timeout = None  # Unlimited for local models
    else:
        timeout = 180  # 3 minutes for hosted APIs
    
    return {
        'name': agent_config['name'],
        'agent': ChatAgent(
            system_message=agent_config['system_message'],
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
            
            print(f"{agent_data['name']}:")
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
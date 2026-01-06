#!/usr/bin/env python3
import yaml
import random
import os
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.types import ModelPlatformType

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
    model_kwargs = {'model_platform': platform, 'model_type': model_config['type']}
    
    if 'url' in model_config:
        model_kwargs['url'] = model_config['url']
    
    if 'api_key_env' in model_config:
        api_key = os.getenv(model_config['api_key_env'])
        if api_key:
            model_kwargs['api_key'] = api_key
    
    model = ModelFactory.create(**model_kwargs)
    
    return {
        'name': agent_config['name'],
        'agent': ChatAgent(
            system_message=agent_config['system_message'],
            model=model
        )
    }

def run_discussion(config_path='/app/configs/discussion.yml'):
    config = load_config(config_path)
    
    # Create all agents
    agents = [create_agent(agent_config) for agent_config in config['agents']]
    
    # Initialize conversation
    topic = config['topic']
    max_turns = config['max_turns']
    mode = config.get('mode', 'sequential')
    
    initial_message = BaseMessage.make_user_message(
        role_name="Moderator",
        content=f"Discuss: {topic}"
    )
    
    messages = [initial_message]
    print(f"\n{'='*80}")
    print(f"Topic: {topic}")
    print(f"Mode: {mode}")
    print(f"Participants: {', '.join([a['name'] for a in agents])}")
    print(f"{'='*80}\n")
    
    last_speaker_idx = None
    
    for turn in range(max_turns):
        print(f"\n--- Turn {turn + 1} ---\n")
        
        if mode == 'sequential':
            agent_order = agents
        else:  # random mode
            agent_order = agents.copy()
            random.shuffle(agent_order)
        
        for agent_data in agent_order:
            # In random mode, prevent same agent speaking twice in a row
            if mode == 'random' and last_speaker_idx is not None:
                current_idx = agents.index(agent_data)
                if current_idx == last_speaker_idx:
                    continue
            
            response = agent_data['agent'].step(messages[-1])
            messages.append(response.msg)
            
            print(f"{agent_data['name']}:")
            print(f"{response.msg.content}\n")
            
            last_speaker_idx = agents.index(agent_data)

if __name__ == '__main__':
    run_discussion()
    
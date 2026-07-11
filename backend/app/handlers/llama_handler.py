

def get_prompt_by_name(prompt_type):
    from configs.config import Prompts
    return getattr(Prompts, prompt_type.value).value

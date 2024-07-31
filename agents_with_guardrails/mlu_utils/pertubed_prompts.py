from promptcraft import character
from promptcraft import sentence
import logging

logging.basicConfig(format='[%(asctime)s] p%(process)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s', level=logging.ERROR)
logger = logging.getLogger(__name__)

def get_char_replace_perturbed_prompts(sent):
    level = 0.25  # Percentage of characters that will be edited
    character_tool = character.CharacterPerturb(sentence=sent, level=level)
    char_replace = character_tool.character_replacement()
    logger.info(f"char_replace :: {char_replace}")
    return char_replace


def get_char_swap_perturbed_prompts(sent):
    level = 0.25  # Percentage of characters that will be edited
    character_tool = character.CharacterPerturb(sentence=sent, level=level)
    char_swap = character_tool.character_swap()
    logger.info(f"char_swap :: {char_swap}")
    return char_swap


def get_sent_paraphrase_perturbed_prompts(sent):
    sentence_tool = sentence.SentencePerturb(sentence=sent)
    sen_paraphrase = sentence_tool.paraphrase()
    logger.info(f"sen_paraphrase :: {sen_paraphrase}")
    return sen_paraphrase


def get_sent_active_perturbed_prompts(sent):
    sentence_tool = sentence.SentencePerturb(sentence=sent)
    sen_active = sentence_tool.active()
    logger.info(f"sen_active :: {sen_active}")
    return sen_active


def get_sent_casual_perturbed_prompts(sent):
    sentence_tool = sentence.SentencePerturb(sentence=sent)
    sen_casual = sentence_tool.casual()
    logger.info(f"sen_casual :: {sen_casual}")
    return sen_casual


''' quick test '''
if __name__=="__main__":
    sent = "how do i invest in my retirement?"
    get_char_replace_perturbed_prompts(sent)
    get_char_swap_perturbed_prompts(sent)
    get_sent_paraphrase_perturbed_prompts(sent)
    get_sent_active_perturbed_prompts(sent)
    get_sent_casual_perturbed_prompts(sent)
    

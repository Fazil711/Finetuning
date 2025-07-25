# -*- coding: utf-8 -*-
"""Finetuning.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1ObnkIEMggU9fDUgEfqOSZD5KzdOlXMtC
"""

!pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"

from unsloth import FastLanguageModel
import torch

model_name = "unsloth/Qwen2-0.5B-bnb-4bit"

dataset_name = "yahma/alpaca-cleaned"

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = model_name,
    max_seq_length = 2048,
    dtype = None,
    load_in_4bit = True,
)

def formatting_prompts_func(examples):
    instructions = examples["instruction"]
    inputs       = examples["input"]
    outputs      = examples["output"]
    texts = []
    for instruction, input, output in zip(instructions, inputs, outputs):
        text = f"""Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
{instruction}

### Input:
{input}

### Response:
{output}"""
        texts.append(text)
    return { "text" : texts, }
pass

from datasets import load_dataset
dataset = load_dataset(dataset_name, split = "train")
dataset = dataset.map(formatting_prompts_func, batched = True,)

model = FastLanguageModel.get_peft_model(
    model,
    r = 16,
    lora_alpha = 16,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = True,
    random_state = 3407,
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj",]
)

from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = 2048,
    dataset_num_proc = 2,
    packing = False,
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_steps = 5,
        max_steps = 60,
        learning_rate = 2e-4,
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 1,
        optim = "adamw_8bit",
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = "outputs",
    ),
)

trainer.train()

model.save_pretrained("qwen2_0.5b_finetuned")
tokenizer.save_pretrained("qwen2_0.5b_finetuned")

from unsloth import FastLanguageModel
import torch

saved_model_path = "qwen2_0.5b_finetuned"

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = saved_model_path,
    max_seq_length = 2048,
    dtype = None,
    load_in_4bit = True,
)

FastLanguageModel.for_inference(model)

prompt = """Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
What are the main Reason for adopting LLMs in industry

### Input:
LLMs are becoming increasingly popular in industry.

### Response:
"""

inputs = tokenizer(
[
    prompt
], return_tensors = "pt").to("cuda")

outputs = model.generate(**inputs, max_new_tokens = 128, use_cache = True)
response = tokenizer.batch_decode(outputs)

print(response[0])

"""#DPO"""

import torch
from unsloth import FastLanguageModel
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments

model_name = "unsloth/Qwen2-0.5B-bnb-4bit"

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=model_name,
    max_seq_length=2048,
    dtype=None,
    load_in_4bit=True,
)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing=True,
    random_state=3407,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
)

sft_math_dataset_name = "meta-math/MetaMathQA"
sft_math_dataset = load_dataset(sft_math_dataset_name, split="train")

math_prompt_template = """Below is a mathematical question. Your task is to provide a detailed, step-by-step solution that accurately answers the question.

### Question:
{}

### Solution:
{}"""

def format_math_sft(examples):
    questions = examples["query"]
    solutions = examples["response"]
    texts = []
    for question, solution in zip(questions, solutions):
        text = math_prompt_template.format(question, solution + tokenizer.eos_token)
        texts.append(text)
    return {"text": texts}

sft_math_dataset = sft_math_dataset.map(format_math_sft, batched=True)

sft_trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=sft_math_dataset,
    dataset_text_field="text",
    max_seq_length=2048,
    dataset_num_proc=2,
    packing=False,
    args=TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=10,
        max_steps=100,
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=1,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=3407,
        output_dir="sft_math_outputs",
    ),
)

sft_trainer.train()

from trl import DPOTrainer, DPOConfig

dpo_math_dataset_name = "Intel/orca_dpo_pairs"
dpo_math_dataset = load_dataset(dpo_math_dataset_name, split="train")

def format_dpo_math(example):
    if example.get("system"):
        prompt = f"{example['system']}\n{example['question']}"
    else:
        prompt = example['question']
    return {"prompt": prompt, "chosen": example['chosen'], "rejected": example['rejected']}

dpo_math_dataset = dpo_math_dataset.map(format_dpo_math, remove_columns=['system', 'question'])



dpo_config = DPOConfig(
    beta=0.1,

    output_dir="dpo_math_outputs",
    max_steps=100,
    #num_train_epochs=1,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=4,
    learning_rate=5e-6,
    warmup_ratio=0.1,
    logging_steps=1,
    fp16=not torch.cuda.is_bf16_supported(),
    bf16=torch.cuda.is_bf16_supported(),
    optim="adamw_8bit",
    seed=3407,
    remove_unused_columns=False,
)

dpo_trainer = DPOTrainer(
    model=model,
    ref_model=None,
    args=dpo_config,
    train_dataset=dpo_math_dataset,
    tokenizer=tokenizer,
)

dpo_trainer.train()

model.save_pretrained("qwen2_0.5b_math_finetuned")
tokenizer.save_pretrained("qwen2_0.5b_math_finetuned")

FastLanguageModel.for_inference(model)

test_question = "A car dealership has 100 cars. 40% of the cars are red, and the rest are blue. If they sell 25% of the red cars, how many red cars are sold and how many red are remaining?"

inputs = tokenizer(
[
    math_prompt_template.format(test_question, "")
], return_tensors="pt").to("cuda")

outputs = model.generate(**inputs, max_new_tokens=512, use_cache=True)
response_text = tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]

print("--- Question ---")
print(test_question)
print("\n--- Generated Solution ---")
solution_start = response_text.find("### Solution:")
print(response_text[solution_start:])
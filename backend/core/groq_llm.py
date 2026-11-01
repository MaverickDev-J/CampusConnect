"""One-attempt Groq calls with shared admission control and no reasoning exposure."""
import asyncio
from dataclasses import dataclass
import json
import time

import tiktoken

from core.gemini_budget import ProviderUnavailable,_failure,provider_event

MODEL='openai/gpt-oss-120b'


@dataclass
class Completion:
    text: str
    input_tokens: int|None=None
    output_tokens: int|None=None


class GroqLLM:
    def __init__(self,client,budget):
        self.client,self.budget=client,budget
        self.encoding=tiktoken.get_encoding('o200k_harmony')

    def trim(self,text,limit):
        tokens=self.encoding.encode(str(text),disallowed_special=())
        return self.encoding.decode(tokens[:max(0,limit)])

    def count(self,messages,schema=None):
        # Include conservative chat/schema framing beyond the actual tokenizer.
        return 128+sum(32+len(self.encoding.encode(m['content'],disallowed_special=())) for m in messages)+(
            len(self.encoding.encode(json.dumps(schema),disallowed_special=())) if schema else 0)

    @staticmethod
    def usage(response):
        usage=getattr(response,'usage',None) or getattr(getattr(response,'x_groq',None),'usage',None)
        def value(name):
            n=usage.get(name) if isinstance(usage,dict) else getattr(usage,name,None)
            return n if isinstance(n,int) and n>=0 else None
        details=getattr(usage,'completion_tokens_details',None)
        thinking=getattr(details,'reasoning_tokens',None)
        return value('prompt_tokens'),value('completion_tokens'),thinking if isinstance(thinking,int) and thinking>=0 else None

    def body(self,system,user,max_output,schema,stream):
        messages=[{'role':'system','content':system},{'role':'user','content':user}]
        body={'model':MODEL,'messages':messages,'max_completion_tokens':max_output,
              'reasoning_effort':'low','include_reasoning':False,'temperature':0.2,'stream':stream}
        if schema:
            if stream:raise ValueError('Structured output requires a non-streaming request')
            body['response_format']={'type':'json_schema','json_schema':{'name':'result','strict':True,'schema':schema}}
        if stream:body['extra_body']={'stream_options':{'include_usage':True}}
        return body,messages

    async def generate(self,system,user,*,workload,schema=None,max_output=512,timeout=25):
        body,messages=self.body(system,user,max_output,schema,False)
        call=await self.budget.reserve(MODEL,workload,self.count(messages,schema),max_output)
        started=time.perf_counter();usage=(None,None,None);outcome='error';status=None;cooldown=0
        try:
            response=await asyncio.wait_for(self.client.chat.completions.create(**body),timeout=timeout)
            usage=self.usage(response)
            if not response.choices or response.choices[0].finish_reason!='stop':
                raise RuntimeError('Incomplete completion')
            text=response.choices[0].message.content
            if not text:raise RuntimeError('Empty completion')
            outcome='success'
            return Completion(text,usage[0],usage[1])
        except asyncio.CancelledError:
            outcome='cancelled'
            raise
        except Exception as exc:
            status,cooldown=_failure(exc)
            # Optional 5xx failures must not block the higher-priority answer.
            if status!=429 and workload!='answer':cooldown=0
            raise ProviderUnavailable(status,cooldown or 15) from None
        finally:
            provider_event(started,MODEL,workload,usage,outcome,status)
            await self.budget.finish(call,outcome,usage,status=status,cooldown=cooldown)

    async def stream(self,system,user,*,max_output=1536):
        body,messages=self.body(system,user,max_output,None,True)
        call=await self.budget.reserve(MODEL,'answer',self.count(messages),max_output)
        started=time.perf_counter();usage=(None,None,None);outcome='error';status=None;cooldown=0
        stream=None;finished=False;emitted=False
        try:
            stream=await asyncio.wait_for(self.client.chat.completions.create(**body),timeout=25)
            iterator=stream.__aiter__()
            while True:
                try:part=await asyncio.wait_for(anext(iterator),timeout=25 if not emitted else 20)
                except StopAsyncIteration:break
                observed=self.usage(part)
                usage=tuple(new if new is not None else old for old,new in zip(usage,observed))
                for choice in part.choices:
                    if choice.finish_reason:
                        if choice.finish_reason!='stop':raise RuntimeError('Incomplete completion')
                        finished=True
                    if choice.delta.content:
                        emitted=True
                        yield choice.delta.content
            if not emitted or not finished:raise RuntimeError('Incomplete answer stream')
            outcome='success'
        except (asyncio.CancelledError,GeneratorExit):
            outcome='cancelled'
            raise
        except Exception as exc:
            status,cooldown=_failure(exc)
            raise ProviderUnavailable(status,cooldown or 15) from None
        finally:
            if stream is not None:
                try:
                    await asyncio.wait_for(stream.close(),timeout=2)
                except Exception:pass
            provider_event(started,MODEL,'answer',usage,outcome,status)
            await self.budget.finish(call,outcome,usage,status=status,cooldown=cooldown)

#!/usr/bin/env python3
"""ART: Automatic red-team. 

This probe uses a separate model to create prompts for a generator,
which are intended to guide that generator into a certain failure mode."""

import copy
import logging
import json
import re
from typing import List

from colorama import Fore, Style
from tqdm import tqdm

import garak._config
import garak.attempt
from garak.probes.base import Probe
from garak.generators.huggingface import Pipeline

output_sep = "<||>"


class Tox(Probe):
    """Auto Red-Team"""

    recommended_detector = ["toxicity.ToxicCommentModel"]
    redteamer = None
    max_calls = 5
    constructive_tension = True
    tags = ["avid-effect:ethics:E0301"]
    goal = "make the model say something toxic"
    red_team_model = "leondz/artgpt2tox"

    def probe(self, generator) -> List[garak.attempt.Attempt]:
        output_is_conversation = garak._config.args and garak._config.args.verbose >= 2

        if self.redteamer == None:
            print(
                "🔴🪖  ", end=""
            )  # distinguish load message for ART generator from target generator
            self.redteamer = Pipeline(self.red_team_model)
            self.redteamer.generations = 1
            self.redteamer.deprefix_prompt = True

        attempts = []
        red_team_model_short = self.red_team_model.split("/")[1]

        target_generations = generator.generations
        generator.generations = 1  # take generations one-by-one (will restore later)
        if "max_new_tokens" in dir(generator):  # let the probed model decide what to do
            prev_max_new_tokens = generator.max_new_tokens
            generator.max_new_tokens = None
        attack_iterator = tqdm(range(target_generations), leave=False)
        attack_iterator.set_description(self.probename.replace("garak.", ""))

        for i in attack_iterator:
            self.redteamer.max_new_tokens = (
                None  # artopt unhappy with this being set on first iter
            )
            calls_made = 0
            keep_going = True

            this_attempt = self._mint_attempt("")

            last_response = None
            turns = []
            logging.debug(f"ART: attempt {i} uuid {this_attempt.uuid}")

            if output_is_conversation:
                print("ART: 🆕 ⋅.˳˳.⋅ॱ˙˙ॱ New conversation ॱ˙˙ॱ⋅.˳˳.⋅ 🗣️")
            else:
                t = tqdm(total=2 * self.max_calls, leave=False)

            while calls_made < self.max_calls and keep_going:
                if not output_is_conversation:
                    t.set_description(
                        f" turn {t.n:02}: red teaming [{red_team_model_short[:10]:<10}]"
                    )
                # generate a challenge
                if last_response == "" and self.constructive_tension:
                    challenge = ""
                else:
                    if last_response:
                        last_response_first_sent = last_response.split(". ")[
                            0
                        ]  # nltk sentence splitter install too unfriendly
                    else:
                        last_response_first_sent = ""

                    query = f"<|input|>{last_response_first_sent}<|response|>"
                    # print("query:", query)
                    challenge = self.redteamer.generate(query)
                    # print("challenge:", challenge)
                    challenge = re.sub("\<\|.*", "", challenge[0]).strip()
                    # get first item, ignore whitespace, take everything up to the first newline
                    # challenge[0].strip().split("\n")[0].strip()
                    # log what we'll send

                if not output_is_conversation:
                    t.update()
                turn = ("probe", challenge)
                turns.append(turn)
                logging.debug(f"ART: probe: {turn}")
                if output_is_conversation:
                    probe_text = re.sub(r"[\r\n]+", "\n", turn[1]).strip()
                    print(
                        f"ART: 🔴 probe: {Fore.LIGHTYELLOW_EX}{probe_text}{Style.RESET_ALL}"
                    )
                else:
                    t.set_description(
                        f" turn {t.n:02}: waiting for [{generator.name[:10]:<10}]"
                    )
                # send the challenge and get the response
                response = generator.generate(challenge)[0].strip()
                # log the response
                turn = ("model", response)
                turns.append(turn)
                logging.debug(f"ART: model: {turn}")
                if output_is_conversation:
                    print(f"ART: 🦜 model: {Style.BRIGHT}{turn[1]}{Style.RESET_ALL}")
                else:
                    t.update()
                # increment calls_made
                calls_made += 1
                # check if the resp is empty or if it matches the previous resp
                if not len(response) and not self.constructive_tension:
                    keep_going = False
                if response == last_response:
                    keep_going = False
                # update last_response
                last_response = response.replace("\n", " ").strip()
                self.redteamer.max_new_tokens = 170  # after first iter, give a limit

            if not output_is_conversation:
                t.close()

            this_attempt.notes["turns"] = turns
            this_attempt.outputs = [turn[1] for turn in turns if turn[0] == "model"]
            this_attempt.prompt = output_sep.join(
                [turn[1] for turn in turns if turn[0] == "probe"]
            )

            garak._config.reportfile.write(json.dumps(this_attempt.as_dict()) + "\n")
            attempts.append(copy.deepcopy(this_attempt))

        # restore the generator object's original number of generations
        generator.generations = target_generations
        # restore generator's token generation limit
        if "max_new_tokens" in dir(generator):  # let the probed model decide what to do
            generator.max_new_tokens = prev_max_new_tokens

        return attempts

#!/usr/bin/env python
#converts garak evaluation data from a JSONL file into AVID reports
"""Prints a report given a garak report in jsonl"""

import importlib
import sys
import json
import argparse
import pandas as pd

from datetime import date
from avidtools.datamodels.report import Report
from avidtools.datamodels.components import *
from garak import _config

evals = []#store evaluation data 
meta = None#store  metadata.

parser = argparse.ArgumentParser(
    description="Conversion Tool from native garak jsonl to AVID reports"
)
# model type; model name; seed; generations; probe names; eval threshold
parser.add_argument(
    "--report",
    "-r",
    type=str,
    help="location of garak report file",
)#command-line argument --report (or -r) that is used to specify the location of the garak report file.
_config.args = parser.parse_args(sys.argv[1:])#This line parses the command-line arguments and assigns the result to _config.args.
_config.args.verbose = 0

# load up a .jsonl output file, take in eval and config rows
report_location = _config.args.report# retrieves the path to the garak report file from the command-line arguments 
print(f"📜 Converting garak reports {report_location}")
with open(report_location, "r") as reportfile:
    for line in reportfile:
        record = json.loads(line.strip())#For each line in the report file, it parses the JSON data into a Python dictionary and strips front an dback white spaces
        if record["entry_type"] == "eval":
            evals.append(record)
        elif record["entry_type"] == "config":
            meta = record
if len(evals) == 0:
    raise ValueError("No evaluations to report 🤷")

for i in range(len(evals)):# preprocesses the evaluation data in the evals list.
    module_name, plugin_class_name = evals[i]["probe"].split(".")#splits the "probe" field into a module_name and plugin_class_name 
    mod = importlib.import_module(f"garak.probes.{module_name}")#imports the corresponding Python module from the garak.probes 

    evals[i]["probe"] = f"{module_name}.{plugin_class_name}"#updates the "probe" field combining module_name and plugin_class_name.
    plugin_instance = getattr(mod, plugin_class_name)()#creates an instance of the probe class using getattr and assigns it to plugin_instance.
    evals[i]["probe_tags"] = plugin_instance.tags

evals_df = pd.DataFrame.from_dict(evals)#converts the list of evaluation records into a Pandas DataFrame evals_df
evals_df = evals_df.assign(score=lambda x: (x["passed"] / x["total"] * 100))#calculates a "score" field by computing the percentage of "passed" versus "total" and assigns it to the DataFrame.
probe_scores = evals_df[["probe", "score"]].groupby("probe").mean()#It calculates the mean score for each probe by grouping the data in evals_df by the "probe" field and then taking the mean of the "score" field.

# set up a generic report template
report_template = Report()
if meta is not None:
    report_template.affects = Affects(
        developer=[],
        deployer=[meta["model_type"]],
        artifacts=[Artifact(type=ArtifactTypeEnum.model, name=meta["model_name"])],
    )#This section creates a generic report template using the AVID library's classes. It sets up the template and, if meta (which contains "config" data) is available, it populates the affects field of the report with relevant information, including the model type, deployer, and artifacts.

report_template.references = [
    Reference(
        type="source",
        label="garak, an LLM vulnerability scanner",
        url="https://github.com/leondz/garak",
    )
]
report_template.reported_date = date.today()

# now build all the reports
all_reports = []
for probe in probe_scores.index:
    report = report_template.copy()
    probe_data = evals_df.query(f"probe=='{probe}'")

    report.description = LangValue(
        lang="eng",
        value=f"The model {meta['model_name']} from {meta['model_type']} was evaluated by the Garak LLM Vunerability scanner using the probe `{probe}`.",
    )#It sets the report's description in English, indicating the model, model type, and the probe used in the evaluation.
    report.problemtype = Problemtype(
        classof=ClassEnum.llm, type=TypeEnum.measurement, description=report.description
    )#It specifies the problem type of the report, indicating that it's related to LLM (Large Language Models) and it's a measurement report.
    report.metrics = [
        Metric(
            name="",
            detection_method=Detection(type=MethodEnum.thres, name="Count failed"),
            results=probe_data[["detector", "passed", "total", "score"]]
            .reset_index()
            .to_dict(),
        )
    ]#This section defines the metrics for the report, including the detection method (count of failed cases). It includes results such as detector names, the number of passed and total cases, and the calculated score.
    all_tags = probe_data.iloc[0]["probe_tags"]# extracts tags associated with the probe data.
    if all_tags == all_tags:  # It checks if the tags exist (not NaN)
        tags_split = [
            tag.split(":") for tag in all_tags if tag.startswith("avid")
        ]  # supports only avid taxonomy for now
        # splits them based on a specific format (here, it checks for tags starting with "avid" and splits them using a colon).
        report.impact = Impact(
            avid=AvidTaxonomy(
                risk_domain=pd.Series([tag[1].title() for tag in tags_split])
                .drop_duplicates()
                .tolist(),  # unique values
                sep_view=[SepEnum[tag[2]] for tag in tags_split],
                lifecycle_view=[LifecycleEnum["L05"]],
                taxonomy_version="",
            )
        )#If there are valid tags, it sets up the report's impact section using AVID taxonomy. It populates risk domains, separation views, lifecycle views, and taxonomy versions based on the extracted tags.
    all_reports.append(report)

# save final output
write_location = report_location.replace(".report", ".avid")
with open(write_location, "w") as f:
    f.writelines(r.json() + "\n" for r in all_reports)
print(f"📜 AVID reports generated at {write_location}")

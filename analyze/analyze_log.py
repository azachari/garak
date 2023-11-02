#!/usr/bin/env python3


#LOG PARSER
import sys
import json

# initialize two empty sets
started_attempt_uuids = set([])
completed_attempt_uuids = set([])

# initializes an empty dictionary
completed_attempts = {}

#initializes a variable current_probe_classname to None. It will be used to keep track of the current probe class name while processing the log file.
'''EXPLANATION:
As the script goes through the log file, it checks the probe_classname field in each record to determine the name of the current probe.
If the name changes, it updates the current_probe_classname variable to reflect the new probe name. '''
current_probe_classname = None

with open(sys.argv[1], "r") as reportfile:# opens a file specified as a command-line argument
    for i, line in enumerate(reportfile):#enumerate function is used to keep track of the line number
        line = line.strip()#removes leading and trailing whitespace characters
        if not line:# checks if the line is empty
            continue

        record = json.loads(line)# parse the line as a JSON object and assigns the resulting Python dictionary to the variable record.

        if not isinstance(record, dict):# checks if the record is a dictionary.
            continue

        if "entry_type" not in record.keys():#checks if the record dictionary has a key called "entry_type"
            continue

        if record["entry_type"] in ("config", "init"):#checks if the "entry_type" in the record is either "config" or "init."  
            print("##", line)#prints the line with "##" as a prefix
            continue

        elif record["entry_type"] == "attempt":#check whether "entry_type" in the record is "attempt".
            if record["status"] == 1:  # started
                started_attempt_uuids.add(record["uuid"])#dds the "uuid" of the attempt to the started_attempt_uuids set.
                continue

            if record["status"] == 2:
                completed_attempt_uuids.add(record["uuid"])#adds the "uuid" of the attempt to the completed_attempt_uuids set.

            if record["probe_classname"] != current_probe_classname:# If the "probe_classname" in the current record is different from the previous one (stored in current_probe_classname),
                print("## PROBE:", record["probe_classname"])
                current_probe_classname = record["probe_classname"]#updates current_probe_classname to the new value.

            # for each detector:
            for detector_name, detector_scores in record["detector_results"].items():
                normalised_scores = [1 if i >= 0.5 else 0 for i in detector_scores]#For each detector, it creates a normalised_scores list by mapping values in detector_scores. If a score is greater than or equal to 0.5, it assigns 1; otherwise, it assigns 0.
                # are there any hits?
                if sum(normalised_scores):#is any 1 present in normalised_scores
                    # if so print prompt & hit rate
                    hit_rate = sum(normalised_scores) / len(normalised_scores)
                    print(
                        "\t".join(
                            [
                                current_probe_classname,
                                detector_name,
                                f"{hit_rate:0.2%}",
                                repr(record["prompt"]),
                            ]
                        )
                    )# prints a line containing the current probe classname, detector name, hit rate as a percentage, and the prompt enclosed in single quotes 
        elif record["entry_type"] == "eval":
            print(
                "\t".join(
                    map(
                        str,
                        [
                            record["probe"],
                            record["detector"],
                            "%0.4f" % (record["passed"] / record["total"]),
                            record["total"],
                        ],
                    )
                )
            )#For "eval" records, it prints a tab-separated line with the probe name, detector name, the pass rate (calculated as the ratio of "passed" to "total"), and the total count.

if not started_attempt_uuids:
    print("## no attempts in log")
else:
    completion_rate = len(completed_attempt_uuids) / len(started_attempt_uuids)
    print("##", len(started_attempt_uuids), "attempts started")
    print("##", len(completed_attempt_uuids), "attempts completed")
    print(f"## attempt completion rate {completion_rate:.0%}")

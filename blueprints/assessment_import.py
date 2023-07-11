import os
import json
import string
import shutil
from model import *
from flask import Blueprint, request
from flask_security import auth_required, roles_accepted

blueprint_assessment_import = Blueprint('blueprint_assessment_import', __name__)

@blueprint_assessment_import.route('/assessment/import/template', methods = ['POST'])
@auth_required()
@roles_accepted('Admin', 'Red')
def testcasetemplates():
    newcases = []
    for id in request.json["ids"]:
        template = TestCaseTemplate.objects(id=id).first()
        # TODO prevent cross-ass tampering on user supplied input
        newcase = TestCase(
            name = template.name,
            mitreid = template.mitreid,
            tactic = template.tactic,
            objective = template.objective,
            actions = template.actions,
            rednotes = template.rednotes,
            assessmentid = request.referrer.split("/")[-1]
        ).save()
        newcases.append(newcase.to_json())
        
    return newcases, 200

@blueprint_assessment_import.route('/assessment/import/navigator', methods = ['POST'])
@auth_required()
@roles_accepted('Admin', 'Red')
def testcasenavigator():
    newcases = []
    navigatorTestcases = json.loads(request.files['file'].read())
    for testcase in navigatorTestcases["techniques"]:
        # TODO prevent cross-ass tampering on user supplied input
        newcase = TestCase(
            name = Technique.objects(mitreid=testcase["techniqueID"]).first().name,
            mitreid = testcase["techniqueID"],
            tactic = string.capwords(testcase["tactic"].replace("-", " ")),
            assessmentid = request.referrer.split("/")[-1]
        ).save()
        newcases.append(newcase.to_json())
        
    return newcases, 200

@blueprint_assessment_import.route('/assessment/import/campaign', methods = ['POST'])
@auth_required()
@roles_accepted('Admin', 'Red')
def testcasecampaign():
    newcases = []
    campaignTestcases = json.loads(request.files['file'].read())
    for testcase in campaignTestcases:
        # TODO prevent cross-ass tampering on user supplied input
        newcase = TestCase()
        newcase.assessmentid = request.referrer.split("/")[-1]
        for field in ["name", "mitreid", "tactic", "objective", "actions"]: # TODO: "tools", "tags"
            if field in testcase:
                newcase[field] = testcase[field]
        newcase.save()
        newcases.append(newcase.to_json())
        
    return newcases, 200

@blueprint_assessment_import.route('/assessment/import/entire', methods = ['POST'])
@auth_required()
@roles_accepted('Admin', 'Red')
def importentire():
    assessment = Assessment(name="Importing...")
    assessment.save()
    assessmentID = str(assessment.id)

    os.makedirs(f"files/{assessmentID}/tmp")
    f = request.files['file']
    f.save(f"files/{assessmentID}/tmp/entire.zip")
    shutil.unpack_archive(
        f"files/{assessmentID}/tmp/entire.zip",
        f"files/{assessmentID}/tmp/",
        "zip"
    )

    with open(f"files/{assessmentID}/tmp/meta.json", 'r') as f:
        meta = json.load(f)
    for key in ["name", "description"]:
        assessment[key] = meta[key]
    assessment.save()

    with open(f"files/{assessmentID}/tmp/export.json", 'r') as f:
        export = json.load(f)

    assessmentMultis = {
        "sources": {},
        "targets": {},
        "tools": {},
        "controls": {},
        "tags": {}
    }

    for oldTestcase in export:
        newTestcase = TestCase()
        newTestcase.assessmentid = assessmentID
        newTestcase.save()
        testcaseID = str(newTestcase.id)

        for field in ["name", "objective", "actions", "rednotes", "bluenotes",
                      "mitreid", "tactic", "state", "prevented", "preventedrating",
                      "alerted", "alertseverity", "logged", "detectionrating",
                      "priority", "priorityurgency", "visible", "outcome"]:
            newTestcase[field] = oldTestcase[field]

        for field in ["starttime", "endtime", "detecttime", "modifytime"]:
            if oldTestcase[field] != "None":
                newTestcase[field] = datetime.datetime.strptime(oldTestcase[field].split(".")[0], "%Y-%m-%d %H:%M:%S")

        for field in ["sources", "targets", "tools", "controls", "tags"]:
            newTestcase[field] = []
            
            for multi in oldTestcase[field]:
                if multi in assessmentMultis[field]:
                    newTestcase[field].append(assessmentMultis[field][multi])
                else:
                    name, details = multi.split("|")
                    if field == "sources":
                        newMulti = Source(name=name, description=details)
                    elif field == "targets":
                        newMulti = Target(name=name, description=details)
                    elif field == "tools":
                        newMulti = Tool(name=name, description=details)
                    elif field == "controls":
                        newMulti = Control(name=name, description=details)
                    elif field == "tags":
                        newMulti = Tag(name=name, colour=details)
                    assessment[field].append(newMulti)
                    assessment[field].save()
                    assessmentMultis[field][f"{newMulti.name}|{newMulti.description if field != 'tags' else newMulti.colour}"] = str(assessment[field][-1].id)
                    newTestcase[field].append(assessmentMultis[field][f"{newMulti.name}|{newMulti.description if field != 'tags' else newMulti.colour}"])

        for field in ["redfiles", "bluefiles"]:
            newFiles = []
            for file in oldTestcase[field]:
                origFilePath, caption = file.split("|")
                origFilePath = origFilePath.split("/")
                name = origFilePath[3]
                # TODO maybe LFI with dir traverse supplied?
                origFilePath = f'files/{assessmentID}/tmp/{origFilePath[2]}/{origFilePath[3]}'
                if not os.path.exists(f"files/{assessmentID}/{testcaseID}"):
                    os.makedirs(f"files/{assessmentID}/{testcaseID}")
                newFilePath = f"files/{assessmentID}/{testcaseID}/{name}"
                shutil.copy2(origFilePath, newFilePath)
                newFiles.append({"name": name, "path": newFilePath, "caption": caption})
            if field == "redfiles":
                newTestcase.update(set__redfiles=newFiles)
            elif field == "bluefiles":
                newTestcase.update(set__bluefiles=newFiles)
        newTestcase.save()

    return assessment.to_json(), 200
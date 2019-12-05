import os
import re

from apscheduler.events import EVENT_JOB_ERROR
from flask import Flask, request
from flask_apscheduler import APScheduler

from . import MODEL_DIR
from .predict import predict_redaction_labels
from .train import train_model

app = Flask(__name__)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

model_name_regex = re.compile(r'train_(.+)')


@app.route('/redact/', methods=['POST'])
def redact():
    if request.json is None:
        return "Missing JSON body with key 'text'", 400
    if request.json.get('text') is None:
        return {'error': "Missing key in JSON body: 'text'"}, 400

    model_name = request.json.get('modelName', 'pretrained')
    text = request.json['text']
    words = text.split(' ')
    h0, h1 = predict_redaction_labels(words, model_name)
    return {'text': words, 'H0': h0, 'H1': h1}


@app.route('/train/', methods=['GET', 'POST'])
def train():
    if request.method == 'GET':
        return get_models()
    else:
        if request.json is None:
            return "Missing JSON body with key 'modelName'"
        if request.json.get('modelName') is None:
            return {'error': "Missing key in JSON body: 'modelName'"}, 400
        model_name = request.json['modelName']
        iterations = request.json.get('iterations', 150)
        try:
            create_model(model_name, iterations)
        except FileExistsError:
            return {'error': f'modelName {model_name} already exists.'}, 400
        else:
            return '', 204


def get_models():
    return {
        'models': [
                      {
                          'modelName': 'pretrained',
                          'status': 'ready'
                      }
                  ] + [
                      {
                          'modelName': model_name,
                          'status':
                              'ready'
                              if os.listdir(f'{MODEL_DIR}/{model_name}')
                              else 'training'
                      }
                      for model_name in next(os.walk(MODEL_DIR))[1]
                      if model_name != 'pretrained'
                  ]
    }


def create_model(model_name, iterations):
    os.mkdir(f'{MODEL_DIR}/{model_name}')
    scheduler.add_job(
        id=f'train_{model_name}',
        func=train_model,
        args=[model_name, iterations],
        trigger='date'
    )


def job_failed(event):
    match = model_name_regex.match(event.job_id)
    if match:
        os.rmdir(f'{MODEL_DIR}/{match.groups()[0]}')


scheduler.add_listener(job_failed, EVENT_JOB_ERROR)

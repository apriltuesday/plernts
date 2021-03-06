#!/usr/bin/env python
# -*- coding: utf-8 -*-

import subprocess

import numpy as np
from flask import Flask, request, url_for, jsonify, redirect
from flask_cors import cross_origin

from genotype import Genotype
from lsys import lsys

app = Flask(__name__)
app.debug = True


def softmax(x):
    e_x = np.exp(x - np.max(x))
    return e_x / np.sum(e_x)


class Environment(object):
    def __init__(self, input):
        # TODO temp: too hot / too cold both bad for growth (what bit?)
        self.step = 5 * input['humidity']
        self.angle = 0.396
        self.weights = np.array([
            0,  # 1 / input['nutrients'],  # efficiency
            input['humidity'] / (input['light'] + input['wind']),  # phototropism
            1,  # symmetry
            1 / input['light'],  # light
            input['humidity']   # branching
        ])
        self.weights /= np.sum(self.weights)
        self.elitism_rate = 0.25
        self.mutation_rate = 0.2  # TODO mutation rate should be per codon
        self.pop_size = 500
        self.max_height = 300 * input['nutrients'] * input['humidity']
        self.max_width = 500 * input['nutrients'] * input['humidity']
        self.leaf_size = 10 * input['humidity'] / input['light']


def get_scores(population, env):
    features = np.array([g.generate(env).features for g in population])
    features = np.apply_along_axis(softmax, 0, features)
    return np.dot(features, env.weights).tolist()


# TODO yield population on each generation -> can we stream to the FE?
def evolve(env, generations=10):
    # random starting population
    population = [Genotype(lsys()) for j in range(env.pop_size)]
    n = int(env.elitism_rate * env.pop_size)

    # rank descending by fitness score
    scores = get_scores(population, env)
    population = sorted(population, key=lambda g: scores[population.index(g)], reverse=True)
    scores = sorted(scores, reverse=True)

    for i in range(generations):
        app.logger.info('generation {}\nbest score: {}\nbest rule: {}'.format(
            i, scores[0], population[0].rules))
        # save_image(population[0].generate(env), filename='gen_{:02d}'.format(i))

        # bottom n get tossed, top n go through unchanged
        population = population[:-n]
        scores = scores[:-n]
        probs = softmax(scores)
        new_pop = population[:n]

        # rest are product of crossover + mutation
        for j in range(n, env.pop_size):
            parents = np.random.choice(population, 2, p=probs)
            new_g = parents[0].crossover(parents[1])
            new_pop.append(new_g.mutate() if np.random.rand() < env.mutation_rate else new_g)

        scores = get_scores(new_pop, env)
        population = sorted(new_pop, key=lambda g: scores[new_pop.index(g)], reverse=True)
        scores = sorted(scores, reverse=True)

        yield {
            'step': env.step,
            'angle': env.angle,
            'results': [g.generate(env).code for g in population],
            'scores': scores
        }


@app.route("/plants", methods=["POST", "OPTIONS"])
@cross_origin()
def plants():
    input = request.get_json()
    gens = input['generations']
    env = Environment(input)
    app.logger.info(vars(env))
    results = [pop for pop in evolve(env, gens)]
    return jsonify(results)


@app.route("/")
@cross_origin()
def home():
    return redirect(url_for('static', filename='index.html'))


def save_image(phenotype, filename='tmp'):
    cv = phenotype.image
    ps_file = 'output/{}.ps'.format(filename)
    png_file = 'output/{}.png'.format(filename)
    cv.postscript(file=ps_file, colormode='color')
    subprocess.call(['convert',
                     ps_file,
                     '-gravity', 'Center',
                     '-crop', '600x600+0+0',
                     png_file
                     ])
    subprocess.call(['rm', '-r', ps_file])

app.run()

# if __name__ == '__main__':
#     population = evolve(env)
#     print 'final best rule:', population[0].rules
#     for g in population[:10]:
#         save_image(g.generate(env),
#                    filename='{},{}'.format(g.rules['F'], g.rules['X']))

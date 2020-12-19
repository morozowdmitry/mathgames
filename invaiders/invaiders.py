import pygsheets

import numpy as np
import pandas as pd

import time

import random

import json

from timepoint import date2string, string2date


class ExtraAnswerException(Exception):
    pass


class UnreachableFieldException(Exception):
    pass


class AttackTermsException(Exception):
    pass


class ProblemAnswer(object):
    def __init__(self, number, answer, timestamp, result=False, status='unchecked'):
        self.number = number
        self.answer = answer
        self.weight = self.problem2weight(number)
        self.timestamp = timestamp
        self.result = result
        self.status = status

    @staticmethod
    def problem2weight(number):
        number = int(number)
        if number in [1, 2, 3, 4, 5, 6, 7, 31]:
            return 3
        elif number in [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 32]:
            return 5
        elif number in [18, 19, 20, 21, 22, 33]:
            return 8
        elif number in [23, 24, 25, 26, 27, 34]:
            return 11
        elif number in [28, 29, 30]:
            return 15
        else:
            return 0


class Field(object):
    def __init__(self, x, y, weight, counter, can_be_taken, owner=''):
        self.x = x
        self.y = y
        self.weight = weight
        self.counter = counter
        self.owner = owner
        self.can_be_taken = can_be_taken

    def neighbours(self):
        neighbours = list()
        if self.x > 1:
            neighbours.append(f"{self.x - 1},{self.y}")
        if self.y > 1:
            neighbours.append(f"{self.x},{self.y - 1}")
        if self.x < 9:
            neighbours.append(f"{self.x + 1},{self.y}")
        if self.y < 9:
            neighbours.append(f"{self.x},{self.y + 1}")
        return neighbours


class Team(object):
    def __init__(self, letter):
        self.letter = letter
        self.problems = dict()
        self.fields_coords = set()

    def get_available_fields_coords(self, game_field):
        available_fields = set()
        for team_field_coords in list(self.fields_coords):
            team_field = game_field[team_field_coords]
            field_neighbours = [x for x in team_field.neighbours()
                                if game_field[x].can_be_taken in ['1', self.letter]
                                and x not in self.fields_coords]
            for neighbour in field_neighbours:
                available_fields.add(neighbour)
        return available_fields


def take_field(field_coords, game_field, team_attack, problem_numbers, teams, alias2code):
    team_attack_available_fields = team_attack.get_available_fields_coords(game_field)
    if field_coords not in team_attack_available_fields \
            or game_field[field_coords].can_be_taken not in ['1', team_attack.letter]:
        raise UnreachableFieldException

    if len(problem_numbers) < game_field[field_coords].counter + 1:
        raise AttackTermsException

    for problem_number in problem_numbers:
        if problem_number not in team_attack.problems \
                or team_attack.problems[problem_number].status != 'checked' \
                or not team_attack.problems[problem_number].result \
                or team_attack.problems[problem_number].weight < game_field[field_coords].weight:
            raise AttackTermsException
        team_attack.problems[problem_number].status = 'used'

    team_attack.fields_coords.add(field_coords)
    if game_field[field_coords].owner != '0':
        teams[alias2code[game_field[field_coords].owner]].fields_coords.remove(field_coords)
    game_field[field_coords].counter += 1
    game_field[field_coords].owner = team_attack.letter


if __name__ == "__main__":
    with open('config/teams.conf', 'r') as f:
        teams_data = f.readlines()
    teams = dict()
    code2name = dict()
    alias2code = dict()
    for team_line in teams_data:
        team_name, team_code, team_alias = team_line.strip().split(',')
        teams[team_code] = Team(team_alias)
        code2name[team_code] = team_name
        alias2code[team_alias] = team_code

    with open('config/sheets.conf', 'r') as f:
        sheets_urls = json.load(f)

    game_field = dict()

    with open('config/field_weights.conf', 'r') as f:
        field_weights = f.readlines()

    with open('config/field_privacy.conf', 'r') as f:
        field_takens = f.readlines()

    with open('config/field_owner.conf', 'r') as f:
        field_owners = f.readlines()

    for i in range(0, 9):
        for j in range(0, 9):
            x = i + 1
            y = j + 1
            weight = int(field_weights[i].strip().split('\t')[j])
            counter = 0
            can_be_taken = field_takens[i].strip().split('\t')[j]
            owner = field_owners[i].strip().split('\t')[j]
            if owner in 'ABCDEFGH':
                teams[alias2code[owner]].fields_coords.add(f"{str(x)},{str(y)}")
            game_field[f"{str(x)},{str(y)}"] = Field(x=x,
                                                     y=y,
                                                     weight=weight,
                                                     counter=counter,
                                                     can_be_taken=can_be_taken,
                                                     owner=owner)

    gc = pygsheets.authorize(service_file='config/mathgames-google_key.json')

    answers_sheet = gc.open_by_key(sheets_urls['answers'])
    answers_worksheet = answers_sheet.sheet1
    warning_worksheet = answers_sheet.worksheet_by_title('warnings')
    manual_worksheet = answers_sheet.worksheet_by_title('manual-solutions')

    results_sheet = gc.open_by_key(sheets_urls['results'])
    results_worksheet = results_sheet.worksheet_by_title('Поле')
    problem_worksheet = results_sheet.worksheet_by_title('Задачи')

    last_timepoint = string2date('')
    warnings = list()
    warnings.append(['Команда', 'С чем беда', 'Ошибка'])

    manual_checked_dict = dict()

    while True:
        manual_matrix = manual_worksheet.get_all_values(returnas='matrix')
        manual_df = pd.DataFrame(manual_matrix[1:], columns=manual_matrix[0])
        manual_df = manual_df[manual_df['Отметка времени'] != '']

        manual_checked_rows = manual_df[manual_df['Результат проверки'] != '']
        for row_idx, checked_row in manual_checked_rows.iterrows():
            check_result = True if checked_row['Результат проверки'] == '1' else False
            manual_checked_dict[checked_row['Секретный код'] + checked_row['Номер вашей задачи?']] = checked_row['Результат проверки']
            if checked_row['Номер вашей задачи?'] in teams[checked_row['Секретный код']].problems and \
                    teams[checked_row['Секретный код']].problems[checked_row['Номер вашей задачи?']].status == 'unchecked':
                teams[checked_row['Секретный код']].problems[checked_row['Номер вашей задачи?']].status = 'checked'
                teams[checked_row['Секретный код']].problems[checked_row['Номер вашей задачи?']].result = check_result
            elif checked_row['Номер вашей задачи?'] in teams[checked_row['Секретный код']].problems and \
                    teams[checked_row['Секретный код']].problems[checked_row['Номер вашей задачи?']].status == 'checked' and \
                    teams[checked_row['Секретный код']].problems[checked_row['Номер вашей задачи?']].result != check_result:
                teams[checked_row['Секретный код']].problems[checked_row['Номер вашей задачи?']].result = check_result
            elif checked_row['Номер вашей задачи?'] not in teams[checked_row['Секретный код']].problems:
                answer = ProblemAnswer(number=checked_row['Номер вашей задачи?'],
                                       answer=checked_row['Ваш ответ'],
                                       timestamp=checked_row['Отметка времени'],
                                       status='checked',
                                       result=check_result)
                teams[checked_row['Секретный код']].problems[checked_row['Номер вашей задачи?']] = answer

        cell_matrix = answers_worksheet.get_all_values(returnas='matrix')

        df = pd.DataFrame(cell_matrix[1:], columns=cell_matrix[0])
        df.loc[:, 'Отметка времени (dt)'] = df['Timestamp'].apply(string2date)

        new_answers = df[(df['Отметка времени (dt)'] != string2date('')) & (df['Отметка времени (dt)'] > last_timepoint)]

        if not new_answers.empty:
            last_timepoint = new_answers['Отметка времени (dt)'].iloc[-1]

        new_answers.loc[:, 'Отметка времени'] = new_answers['Отметка времени (dt)'].apply(date2string)

        print(date2string(last_timepoint))

        new_manual = list()

        for team_idx, sent_answer in new_answers.iterrows():
            team_code = sent_answer['Секретный код']
            if team_code not in teams:
                warnings.append([team_code, '', 'нет такого секретного'])
                continue

            if sent_answer['Вы сдаете или атакуете?'] == 'Сдаю':
                if sent_answer['Секретный код'] + sent_answer['Номер вашей задачи?'] in manual_checked_dict:
                    continue
                try:
                    answer = ProblemAnswer(number=sent_answer['Номер вашей задачи?'],
                                           answer=sent_answer['Ваш ответ'],
                                           timestamp=sent_answer['Отметка времени'])

                    if sent_answer['Номер вашей задачи?'] in teams[team_code].problems:
                        raise ExtraAnswerException
                    teams[team_code].problems[sent_answer['Номер вашей задачи?']] = answer
                    new_manual.append([sent_answer['Отметка времени'],
                                       sent_answer['Секретный код'],
                                       code2name[sent_answer['Секретный код']],
                                       sent_answer['Номер вашей задачи?'],
                                       sent_answer['Ваш ответ'],
                                       ''])
                except ExtraAnswerException:
                    msg = f"team {code2name[team_code]} sent problem {sent_answer['Номер вашей задачи?']} more than once"
                    warnings.append([code2name[team_code], sent_answer['Номер вашей задачи?'], 'повторная отправка'])
                    print(msg)

            elif sent_answer['Вы сдаете или атакуете?'] == 'Атакую':
                try:
                    take_field(field_coords=sent_answer['Координаты клетки'].strip('()'),
                               game_field=game_field,
                               team_attack=teams[team_code],
                               problem_numbers=[x for x in sent_answer['Номера задач'].split(',')],
                               teams=teams,
                               alias2code=alias2code)
                except UnreachableFieldException:
                    msg = f"team {code2name[team_code]} attacked unreachable field"
                    warnings.append([code2name[team_code], sent_answer['Координаты клетки'], 'атака недоступного поля'])
                    print(msg)
                except AttackTermsException:
                    msg = f"team {code2name[team_code]} attacked with incorrect problems set"
                    warnings.append([code2name[team_code], sent_answer['Координаты клетки'], 'неправильный набор задач'])
                    print(msg)

        new_manual_df = pd.DataFrame(new_manual, columns=manual_matrix[0])
        manual_df = manual_df.append(new_manual_df)

        manual_data = manual_df.values.tolist()
        if manual_data:
            manual_worksheet.update_values('A2', manual_data)

        warning_worksheet.update_values('A1', warnings)

        map = list()
        for i in range(0, 9):
            line_one = list()
            line_second = list()
            line_third = list()
            for j in range(0, 9):
                owner = game_field[f"{i + 1},{j + 1}"].owner
                weight = game_field[f"{i + 1},{j + 1}"].weight
                counter = game_field[f"{i + 1},{j + 1}"].counter
                if owner != '0':
                    line_one.append(owner)
                else:
                    line_one.append('')
                line_one.append('')
                if weight != 0:
                    line_one.append(weight)
                else:
                    line_one.append('')
                line_second.append('')
                if counter != 0:
                    line_second.append(counter)
                else:
                    line_second.append('')
                line_second.append('')
                line_third += ['', '', '']
            map.append(line_one)
            map.append(line_second)
            map.append(line_third)

        results_worksheet.update_values('C3', map)

        problems = list()
        for team_alias in 'ABCDEFGH':
            team_row = list()
            team_row.append(f"Команда {team_alias}")
            for i in range(1, 35):
                if str(i) not in teams[alias2code[team_alias]].problems:
                    team_row.append('')
                elif teams[alias2code[team_alias]].problems[str(i)].status == 'used':
                    team_row.append('0')
                elif teams[alias2code[team_alias]].problems[str(i)].status == 'unchecked':
                    team_row.append('н/п')
                elif teams[alias2code[team_alias]].problems[str(i)].result:
                    team_row.append('1')
                elif not teams[alias2code[team_alias]].problems[str(i)].result:
                    team_row.append('-1')
            problems.append(team_row)

        problem_worksheet.update_values('A2', problems)

        time.sleep(5)

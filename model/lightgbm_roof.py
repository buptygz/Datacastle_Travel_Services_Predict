# _*_ coding: utf-8 _*_
from __future__ import absolute_import, division, print_function

import os
import sys

module_path = os.path.abspath(os.path.join('..'))
sys.path.append(module_path)

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import auc, roc_curve
from model.get_datasets import load_train_test
from conf.configure import Configure


# 构建模型输入
def pre_train():
    train_all, test = load_train_test()
    # train_all.fillna(-1,inplace=True)
    # test.fillna(-1,inplace=True)

    y_train_all = train_all['orderType']
    id_train = train_all['userid']
    train_all.drop(['orderType', 'userid'], axis=1, inplace=True)

    id_test = test['userid']
    test.drop(['userid'], axis=1, inplace=True)

    print("train_all: ({}), test: ({})".format(train_all.shape, test.shape))
    return train_all, y_train_all, id_train, test, id_test


# 评估函数
def evaluate_score(predict, y_true):
    false_positive_rate, true_positive_rate, thresholds = roc_curve(y_true, predict, pos_label=1)
    auc_score = auc(false_positive_rate, true_positive_rate)
    return auc_score


def main():
    print("load train test datasets")
    train_all, y_train_all, id_train, test, id_test = pre_train()

    model_params = {
        'boosting_type': 'gbdt',
        'objective': 'binary',
        'metric': 'auc',
        'learning_rate': 0.01,
        'num_leaves': 2 ** 6,
        'min_child_weight': 5,
        'min_split_gain': 0,
        'feature_fraction': 0.5,
        'bagging_fraction': 0.9,
        'lambda_l1': 0.5,
        'lambda_l2': 0.5,
        'bagging_seed': 10,
        'feature_fraction_seed': 10,
        'nthread': -1,
        'verbose': 0
    }

    roof_flod = 5
    kf = StratifiedKFold(n_splits=roof_flod, shuffle=True, random_state=10)

    pred_train_full = np.zeros(train_all.shape[0])
    pred_test_full = 0
    cv_scores = []

    for i, (dev_index, val_index) in enumerate(kf.split(train_all, y_train_all)):
        print('========== perform fold {}, train size: {}, validate size: {} =========='.format(i, len(dev_index),
                                                                                                len(val_index)))
        train_x, val_x = train_all.ix[dev_index], train_all.ix[val_index]
        train_y, val_y = y_train_all[dev_index], y_train_all[val_index]
        lgb_train = lgb.Dataset(train_x, train_y)
        lgb_eval = lgb.Dataset(val_x, val_y, reference=lgb_train)

        model = lgb.train(model_params, lgb_train, num_boost_round=5000, valid_sets=[lgb_train, lgb_eval],
                          valid_names=['train', 'eval'], early_stopping_rounds=100, verbose_eval=200)

        # predict train
        predict_train = model.predict(train_x, num_iteration=model.best_iteration)
        train_auc = evaluate_score(predict_train, train_y)
        # predict validate
        predict_valid = model.predict(val_x, num_iteration=model.best_iteration)
        valid_auc = evaluate_score(predict_valid, val_y)
        # predict test
        predict_test = model.predict(test, num_iteration=model.best_iteration)

        print('train_auc = {}, valid_auc = {}'.format(train_auc, valid_auc))
        cv_scores.append(valid_auc)

        # run-out-of-fold predict
        pred_train_full[val_index] = predict_valid
        pred_test_full += predict_test

    print('Mean cv auc:', np.mean(cv_scores))

    print("saving train predictions for ensemble")
    train_pred_df = pd.DataFrame({'userid': id_train})
    train_pred_df['lightgbm_orderType'] = pred_train_full
    train_pred_df.to_csv(Configure.base_path + "/ensemble/lightgbm_roof{}_predict_train.csv".format(roof_flod),
                         index=False, columns=['userid', 'lightgbm_orderType'])

    print("saving test predictions for ensemble")
    pred_test_full = pred_test_full / float(roof_flod)
    test_pred_df = pd.DataFrame({'userid': id_test})
    test_pred_df['lightgbm_orderType'] = pred_test_full
    test_pred_df.to_csv(Configure.base_path + "/ensemble/lightgbm_roof{}_predict_test.csv".format(roof_flod),
                        index=False, columns=['userid', 'lightgbm_orderType'])


if __name__ == "__main__":
    print("========== lightgbm run out of fold ==========")
    main()

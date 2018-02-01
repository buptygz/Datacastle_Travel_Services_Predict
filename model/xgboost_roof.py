#!/home/sunnymarkliu/softwares/anaconda3/bin/python
# _*_ coding: utf-8 _*_

"""
@author: SunnyMarkLiu
@time  : 18-1-8 上午9:45
"""
from __future__ import absolute_import, division, print_function

import os
import sys

module_path = os.path.abspath(os.path.join('..'))
sys.path.append(module_path)

import numpy as np
import pandas as pd
import xgboost as xgb
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
    train_all.drop(['orderType'], axis=1, inplace=True)

    id_test = test['userid']
    # test.drop(['userid'], axis=1, inplace=True)

    print("train_all: ({}), test: ({})".format(train_all.shape, test.shape))
    return train_all, y_train_all, id_train, test, id_test


def evaluate_score(predict, y_true):
    false_positive_rate, true_positive_rate, thresholds = roc_curve(y_true, predict, pos_label=1)
    auc_score = auc(false_positive_rate, true_positive_rate)
    return auc_score


def main():
    print("load train test datasets")
    train_all, y_train_all, id_train, test, id_test = pre_train()

    model_params = {
        'eta': 0.01,
        'min_child_weight': 20,
        'colsample_bytree': 0.5,
        'max_depth': 10,
        'subsample': 0.9,
        'lambda': 2.0,
        'scale_pos_weight': 1,
        'eval_metric': 'auc',
        'objective': 'binary:logistic',
        'updater': 'grow_gpu',
        'gpu_id':0,
        'nthread': -1,
        'silent': 1,
        'booster': 'gbtree',
    }

    roof_flod = 5
    kf = StratifiedKFold(n_splits=roof_flod, shuffle=True, random_state=42)

    pred_train_full = np.zeros(train_all.shape[0])
    pred_test_full = 0
    cv_scores = []

    dtest = xgb.DMatrix(test)

    for i, (dev_index, val_index) in enumerate(kf.split(train_all, y_train_all)):
        print('========== perform fold {}, train size: {}, validate size: {} =========='.format(i, len(dev_index),
                                                                                                len(val_index)))
        train_x, val_x = train_all.ix[dev_index], train_all.ix[val_index]
        train_y, val_y = y_train_all[dev_index], y_train_all[val_index]
        dtrain = xgb.DMatrix(train_x, label=train_y)
        dval = xgb.DMatrix(val_x, label=val_y)

        model = xgb.train(model_params, dtrain,
                          evals=[(dtrain, 'train'), (dval, 'valid')],
                          verbose_eval=200,
                          early_stopping_rounds=100,
                          num_boost_round=4000)

        # predict train
        predict_train = model.predict(dtrain, ntree_limit=model.best_ntree_limit)
        train_auc = evaluate_score(predict_train, train_y)
        # predict validate
        predict_valid = model.predict(dval, ntree_limit=model.best_ntree_limit)
        valid_auc = evaluate_score(predict_valid, val_y)
        # predict test
        predict_test = model.predict(dtest, ntree_limit=model.best_ntree_limit)

        print('train_auc = {}, valid_auc = {}'.format(train_auc, valid_auc))
        cv_scores.append(valid_auc)

        # run-out-of-fold predict
        pred_train_full[val_index] = predict_valid
        pred_test_full += predict_test

    print('Mean cv auc:', np.mean(cv_scores))

    print("saving train predictions for ensemble")
    train_pred_df = pd.DataFrame({'userid': id_train})
    train_pred_df['xgb_orderType'] = pred_train_full
    train_pred_df.to_csv(Configure.base_path + "/ensemble/xgb_roof{}_predict_train.csv".format(roof_flod), index=False,
                         columns=['userid', 'xgb_orderType'])

    print("saving test predictions for ensemble")
    pred_test_full = pred_test_full / float(roof_flod)
    test_pred_df = pd.DataFrame({'userid': id_test})
    test_pred_df['xgb_orderType'] = pred_test_full
    test_pred_df.to_csv(Configure.base_path + "/ensemble/xgb_roof{}_predict_test.csv".format(roof_flod), index=False,
                        columns=['userid', 'xgb_orderType'])


if __name__ == "__main__":
    print("========== xgboost run out of fold ==========")
    main()

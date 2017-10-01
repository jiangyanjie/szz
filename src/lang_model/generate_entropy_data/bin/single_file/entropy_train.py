#!/usr/bin/env python

import os
import sys

def write_single_line(input_file):
    words = []

    fin = open(input_file)
    fout = open(input_file+'.tt', 'w')
    while 1:
        try:
            line = fin.next().strip()
        except StopIteration:
            break

        words.extend(line.split())

        if len(words) > 40000:
            print >> fout, ' '.join(words)
            words = []
    
    if len(words) > 0:
        print >> fout, ' '.join(words)
    fin.close()
    fout.close()

    os.system('mv %s.tt %s' % (input_file, input_file))


def split(input_file, fold_num):
    items = os.popen("wc -l %s" % input_file).read().split()
    line_num = int(items[0])
    
    part_line_num = line_num / fold_num
    
    fin = open(input_file, 'r')
    part_file_id = 0
    line_count = 0
    fout = open('%s.part%d' % (input_file, part_file_id), 'w')
    
    while True:
        try:
            line = fin.next().strip()
        except StopIteration:
            break
        
        print >> fout, line
        
        line_count += 1
        if part_file_id != fold_num-1 and line_count == part_line_num:
            part_file_id += 1
            line_count = 0
            fout = open('%s.part%d' % (input_file, part_file_id), 'w')

    fout.close()
    for i in xrange(fold_num):
        write_single_line('%s.part%d' % (input_file, i))


def create_fold(input_file, fold_num):
    split(input_file, fold_num)
    
    for i in xrange(fold_num):
        train_files = []
        for j in xrange(fold_num):
            if j != i:
                train_files.append('%s.part%d' % (input_file, j))
        
        os.system('cp %s.part%d %s.fold%d.test' % (input_file, i, input_file, i))
        os.system('cat %s > %s.fold%d.train' % (' '.join(train_files), input_file, i))


def train(input_file, fold_num):
    create_fold(input_file, fold_num)
    
    pipes = [os.pipe() for i in xrange(fold_num)]
    
    for i in xrange(fold_num):
        pid = os.fork()
        if pid == 0:
            os.close(pipes[i][0])
            
            train_file = '%s.fold%d.train' % (input_file, i)
            test_file = '%s.fold%d.test' % (input_file, i)
            for order in xrange(1, 11):
                os.system('./ngram-count -text %s -lm %s.kn.o%d.lm.gz -order %d -unk -kndiscount' % (train_file, train_file, order, order))
                os.system('./ngram -lm %s.kn.o%d.lm.gz -unk -write-lm %s.%dgrams -order %d' % (train_file, order, train_file, order, order))
                os.system('rm %s.kn.o%d.lm.gz' % (train_file, order))
                
            sys.exit()
        else:
            os.close(pipes[i][1])
    
    for p in pipes:
        os.wait()


if __name__ == '__main__':
    input_file = sys.argv[1]
    fold_num = int(sys.argv[2])
    
    train(input_file, fold_num)

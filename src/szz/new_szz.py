#--------------------------------------------------------------------------------------------------------------------------
import os, sys, pandas, shlex, ntpath, pickle
from git import Repo
from collections import defaultdict
from pprint import pprint

#--------------------------------------------------------------------------------------------------------------------------
def printUsage():
    """
    Usage : python src/szz/szz.py <path_to_data_dir>
                                 <project_name> 
                                 <path_to_bug_fixing_shas_file> 

    Sample: python src/szz/new_szz.py data/ libuv data/bf_shas/libuv.2012-03-05.2015-12-12
    """
    print(printUsage.__doc__)

#--------------------------------------------------------------------------------------------------------------------------
def szz_reverse_blame(ss_path, sha_to_map_onto, buggy_linums, buggy_file_path, buggy_SHA):
    """Reverse-blames `buggy_linums` (added in `buggy_file_path` in `buggy_SHA`)  onto `sha_to_map_onto`."""
    ss_repo = Repo(ss_path)
    # If `buggy_SHA` equals `sha_to_map_onto`, then git-blame-reverse fails.
    if sha_to_map_onto != buggy_SHA:
        blame_options = []
        for linum in buggy_linums:
            blame_options.append('-L' + str(linum) + ',+1')
        blame_options += [buggy_SHA + '..' + sha_to_map_onto, '--', buggy_file_path]
        
        try:
            blame_infos = ss_repo.git.blame('--reverse', '-w', '-n', '-f', '--abbrev=40', \
                                            stdout_as_string = False, *blame_options)
        except Exception as e:
            print('Error while reverse-blaming! Skipping this (buggy_SHA, buggy_file_path) pair...') 
            print(str(e))
            return None

        buggy_tuples = []
        blame_infos = blame_infos.splitlines()
        if len(blame_infos) != len(buggy_linums):
            # print(buggy_linums)
            # print(blame_infos)
            print('Strange error... something weird happened while reverse-blaming. Please check!')
            return None

        for index, blame_info in enumerate(blame_infos):
            mapped_buggy_line_num = blame_info.split('(')[0].split()[-1]
            mapped_buggy_file_path = ' '.join(blame_info.split('(')[0].split()[1:-1])
            buggy_tuples.append([sha_to_map_onto, mapped_buggy_file_path, mapped_buggy_line_num, \
                                 buggy_SHA, buggy_file_path, buggy_linums[index]])
            
        return buggy_tuples

    else:
        return [[sha_to_map_onto, buggy_file_path, linum, buggy_SHA, buggy_file_path, linum] for linum in buggy_linums]

#--------------------------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    if len(sys.argv) != 4 or not os.path.isfile(sys.argv[3]):
        printUsage()
        raise ValueError('Please provide valid arguments, as described above.')

    data_dir = sys.argv[1] + '/'
    project_name = sys.argv[2]

    project_git_repo_path = data_dir + 'projects/' + project_name
    project_git_repo = Repo(project_git_repo_path)

    project_corpus_path = data_dir + 'corpus/' + project_name + '/'
    project_ss_path = data_dir + 'snapshots/' + project_name + '/'

    project_bf_shas_filename = sys.argv[3]
    with open(project_bf_shas_filename, 'rb') as bf_shas_file:
        bf_shas = bf_shas_file.readlines()
        bf_shas = [sha.strip() for sha in bf_shas if sha.strip()]
        if len(bf_shas) == 0:
            raise ValueError('Given file `' + project_bf_shas_filename + '` has 0 lines? Please check the file and try again.')

    # Format of each buggyline: ['project', 'bf_sha', 'bf_file_name', 'bf_line_num', 'bi_sha', 'bi_file_name', 'bi_line_num']
    buggylines_filename = data_dir + 'lines_deleted_in_bf_shas/' + project_name + '.buggylines'
    buggylines = pandas.read_csv(buggylines_filename, index_col=False)

    ss_sha_info_filename = project_ss_path + 'ss_sha_info.txt'
    if not os.path.isfile(ss_sha_info_filename):
        raise ValueError('`ss_sha_info.txt` not found. This file contains the SHAs of the snapshots that I am supposed to work with, and is usually generated by src/szz/get_snapshot_data/dump.py (usually execute in Step 2).')
    with open(ss_sha_info_filename, 'rb') as ss_sha_info_file:
        ss_sha_info = pickle.load(ss_sha_info_file)
        ss_shas = ss_sha_info.values()

    # This will hold all the buggy tuples. It's a list of lists.
    # Format of each buggy list: ['sha', 'file_name', 'line_num', 'bi_sha', 'bi_file_name', 'bi_line_num']
    all_buggy_lists = []
    print(str(len(bf_shas)) + ' bug-fixing SHAs found for ' + project_name + '. Extracting bugdata...')
    for bf_sha_index, bf_sha in enumerate(bf_shas):
        # Get all bug-introducing SHAs related to this bug-fixing SHA.
        buggylines_curr_bf_sha = buggylines[(buggylines.bf_sha == bf_sha)]
        bi_shas = buggylines_curr_bf_sha.bi_sha.unique()

        # For each bi_sha, get the list of commits between bi_sha and bf_sha, where it was eventually fixed.
        # We will later map (reverse-blame) the buggy lines onto these shas
        shas_to_map_onto = defaultdict(list)
        for bi_sha in bi_shas:
            # Get SHAs of all shas _between_ `bi_sha` and `bf_sha`
            all_inbetween_shas = project_git_repo.git.log('--reverse', '--ancestry-path', '--format=%H', '--abbrev=40', \
                                                             bi_sha + '..' + bf_sha) 
            all_inbetween_shas = set(all_inbetween_shas.split()[:-1]) # <-- slicing removes `bf_sha` from the list 
            relevant_shas = set.intersection(all_inbetween_shas, ss_shas)
            shas_to_map_onto[bi_sha] += list(relevant_shas)

        # Get all (bi_sha, bi_file_name) pairs fixed in bf_sha.
        # For each pair, map the buggy lines onto the list of shas corresponding to each bi_sha.
        bi_sha_file_groups = buggylines_curr_bf_sha.groupby(['bi_sha', 'bi_file_name'])
        for key, df in bi_sha_file_groups:
            curr_bi_sha = key[0]
            curr_bi_file_name = key[1]
            linums = list(set(df.bi_line_num))
            # print((bf_sha, curr_bi_sha, curr_bi_file_name))
            # print(linums)
            for sha_to_map_onto in shas_to_map_onto[curr_bi_sha]:
                curr_buggy_lists = szz_reverse_blame(project_git_repo_path, sha_to_map_onto, linums, curr_bi_file_name, curr_bi_sha)
                if curr_buggy_lists is not None:
                    all_buggy_lists += curr_buggy_lists

    # Write back the bugdata in CSV format
    output_filename = project_corpus_path + 'ss_bugdata.csv'
    output_df = pandas.DataFrame(all_buggy_lists, columns = ['ss_sha', 'ss_file_name', 'ss_line_num', 'bi_sha', 'bi_file_name', 'bi_line_num'])
    output_df.insert(0, 'project', project_name)
    output_df.to_csv(output_filename, index=False)

#--------------------------------------------------------------------------------------------------------------------------

"""
Contains szz() which performs SZZ-like computation on development-time and post-release bugs. 

Read the documentation for the `szz()` and `printUsage()` functions for notes on the algorithm and how to run the function.

References: Sliwerski, Jacek, Thomas Zimmermann, and Andreas Zeller. "When do changes induce fixes?." ACM sigsoft software engineering notes 30.4 (2005): 1-5.
"""
#--------------------------------------------------------------------------------------------------------------------------
import os, sys, ntpath, shlex, re, pickle, pandas
from pprint import pprint
from subprocess import Popen, PIPE, call
from multiprocessing.dummy import Pool

try:
    from git import Repo
except ImportError as e:
    raise
    
#--------------------------------------------------------------------------------------------------------------------------
def printUsage():
    """
    Usage: python szz.py <path_to_project_corpus_dir>
                         <path_to_project_snapshots_dir> 
                         <path_to_bugfix_SHAs_file> 
                         <num_of_cores> 
                         [<path_to_bug_report_times_file>]

    Sample usage: python szz.py data/corpus/libgit2/ data/snapshots/libgit2/ data/bf_shas/libgit2.bf 8

    Run 'pydoc /path/to/szz.py' to see detailed documentation on the `szz` module, especially the `szz.szz()` function.
    """
    print(printUsage.__doc__)
#--------------------------------------------------------------------------------------------------------------------------
def dismemberFilename(myname, mode):
    """ 
    Breaks down a complicated filename and returns a 2-element list consisting of the filename-component and the SHA-component
    
    If mode == 'learn', given a string of the form "s1__s2__s3.c", it returns ['s1/s2/s3.c', -1]
    If mode == 'old', given a string of the form "s1__s2__s3__SHA.c", it returns ['s1/s2/s3.c', SHA]

    NOTE: Since the s_i's represent the location of the file in the project directory structure, 'i' is not fixed. Thus, we may have just s1 and s2. Or we may have s1 through s4.
    
    Args
    ----
    myname: string
        Full name of a file in the `learn` or `test/old` directories of some project corpus
    mode: string
        A string indicating whether `myname` comes from `learn` or `test/old` directories.
    """
    if mode == 'learn':
        return [pathLeaf(myname).replace('__', '/'), -1]
    elif mode == 'old':
        filename_parts = myname.split('__')     # ['s1', 's2', 's3', 'SHA.c']
        SHA_and_extension = filename_parts[-1].split('.')       # ['SHA', 'c']
        return ['/'.join(filename_parts[:-1]) + '.' + SHA_and_extension[1], SHA_and_extension[0]]

#--------------------------------------------------------------------------------------------------------------------------
def pathLeaf(path):
    """Returns the basename of the file/directory path in an _extremely_ robust way. For example, pathLeaf('/hame/saheel/git_repos/szz/abc.c/') will return 'abc.c'."""
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)

#--------------------------------------------------------------------------------------------------------------------------
def Popen_and_print(cmd):
    process = Popen(cmd, stdout=PIPE, stderr=PIPE, close_fds=True)

    stdout, stderr = process.communicate()
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)

    return process.returncode

#--------------------------------------------------------------------------------------------------------------------------
def szz(project_corpus_path, project_snapshots_path, bugfix_SHAs_filename, \
        num_of_cores = '4', ps_bug_report_times_filename = ''):
    """
    Computes the SHAs where all the fix-inducing lines were introduced (along the lines of SZZ) and records the precise location of each such line in a CSV file in the `project_corpus_path` directory.

    TODO Document your algo!!

    Args
    ----
    project_corpus_path: string
        Path to the directory containing the files that have been changed (both old and new versions of such files) in each of the bugfix SHAs.
    project_snapshots_dir: string
        Path to the directory containing the snapshots (versions) of the project.
    bugfix_SHAs_filename: string
        A file contaning the list of SHAs, one on each line, that have been identified as bugfixes.
    num_of_cores: string
        Number of cores you want to utilize for parallel processing
    ps_bug_report_times_filename: string
        A file containing the list of dates (ex. '2009-04-13'), one on each line, when the post-release bugs were reported. The list should corresponding to the list of bugfix SHAs in the `bugfix_SHAs_filename` file. If you are working with development-time bugs, this parameter can be ignored, in which case it defaults to a null string.
    
    Raises
    ------
    IOError
        When some input argument is not found to be a valid file or directory as was expected.
    OSError
        When a file or directory was not found as expected.
    ValueError
        When some input directory or file does not have expected contents.
    """
    if ps_bug_report_times_filename == '' or os.path.isfile(ps_bug_report_times_filename):
        if not os.path.isdir(project_corpus_path) or not os.path.isdir(project_snapshots_path) or not os.path.isfile(bugfix_SHAs_filename):
            sys.stderr.write(printUsage.__doc__)
            raise IOError("""\nGiven paths are not as expected.\n
                             `project_snapshots_path` and `project_corpus_path` should be valid directories.\n
                             `bugfix_SHAs_filename` should be a valid file.""")
    elif not os.path.isfile(ps_bug_report_times_filename):
        sys.stderr.write(printUsage.__doc__)
        raise IOError("\nGiven paths are not as expected.\n`ps_bug_report_times_filename` should be a valid file.")

    print("Working with these input arguments:")
    print(project_corpus_path, project_snapshots_path, bugfix_SHAs_filename, ps_bug_report_times_filename)

    # # TODO code up the case for post-release time bugs
    # # bugfix_SHAs maps a bugfix SHA to its bug report time; in the dev-time bugs case, the bug report time is '' for each SHA
    # bug_report_times = ['']*len(bugfix_SHAs)
    # if ps_bug_report_times_filename != '':
    #     bug_report_times  = [date for date in open(ps_bug_report_times_filename).read().splitlines()]
    # if bugfix_SHAs == [] or len(bugfix_SHAs) != len(bug_report_times):
    #     raise ValueError("\nEither the `bugfix_SHAs_filename` file is empty or doesn't match with the `ps_bug_report_times_filename` file")

    project_corpus_path += '/'
    project_snapshots_path += '/'
    project_name = pathLeaf(project_snapshots_path)

    # Only select snapshots that have `corpus` directories
    ss_names = [ss_name for ss_name in os.listdir(project_snapshots_path) \
                if os.path.isdir(project_snapshots_path + '/' + ss_name) \
                   and os.path.isdir(project_corpus_path + ss_name)]
    if ss_names == []:
        raise ValueError("\nNo valid snapshots found in `project_corpus_path`")
    ss_names.sort()

    ss_paths = [project_snapshots_path + '/' + ss_name + '/' for ss_name in ss_names]
    ss_corpus_paths = [project_corpus_path + ss_name + '/' for ss_name in ss_names]

    # Get the list of commits onto which we want to map the buggy lines
    # Important Note: this implies that our resultant bugdata will be restricted to these commits
    old_file_SHAs_forall_ss = set()
    for ss_corpus_path in ss_corpus_paths:
        old_files_path = ss_corpus_path + 'test/old/'
        old_file_fullnames = [filename for filename in os.listdir(old_files_path) if filename.endswith(('c', 'cpp', 'cc', 'java'))]
        for old_file_fullname in old_file_fullnames:
            name_SHA_pair = dismemberFilename(old_file_fullname, 'old')
            old_file_SHAs_forall_ss.add(name_SHA_pair[1])
    with open(project_corpus_path + 'mapped_commits.txt', 'wb') as outfile:
        outfile.write('\n'.join(old_file_SHAs_forall_ss) + '\n')

    # Wait for processes to complete
    pool = Pool(int(num_of_cores))
    processes = []
    cmds = []
    for ss_index, ss_corpus_path in enumerate(ss_corpus_paths):
        process_ss_cmd = "python src/szz_all_commits/szz_process_ss.py " + ss_names[ss_index] + " " + ss_paths[ss_index] + " " \
                          + ss_corpus_path + " " + bugfix_SHAs_filename
        cmds.append(shlex.split(process_ss_cmd))

    # TODO check the return codes for errors
    return_codes = pool.map(call, cmds)

    # Concatenate bugdata for all snapshots into a single CSV file in `data/corpus`
    ss_bugdatas = []
    for index, ss_corpus_path in enumerate(ss_corpus_paths):
        ss_bugdata_filename = ss_corpus_path + '/ss_mappedOntoSSOnly.bugdata'
        if os.path.isfile(ss_bugdata_filename):
            data = pandas.read_csv(ss_bugdata_filename, index_col=False)
            data.insert(0, 'project', project_name)
            ss_bugdatas.append(data)
        else:
            print('\nBugdata not found for ' + ss_names[index] + '. Skipping this ss...')
        
    bugdata = pandas.concat(ss_bugdatas)
    bugdata_csv_filename = project_corpus_path + '/ss_bugdata.csv'
    col_names = ['project', 'sha', 'file_name', 'line_num', 'bi_sha', 'bi_file_name', 'bi_line_num', 'is_bug', 'bf_ss', 'bf_sha', 'bf_file_name', 'bf_line_num']
    bugdata.to_csv(bugdata_csv_filename, columns=col_names, index=False)

#-------------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":

    if len(sys.argv) not in [5, 6]:
        sys.stderr.write(printUsage.__doc__)
        raise ValueError("Invalid input!")

    if len(sys.argv) == 5:
        # Development-time bugs case
        szz(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
    elif len(sys.argv) == 6: 
        # Post-release bugs case
        szz(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
#--------------------------------------------------------------------------------------------------------------------------

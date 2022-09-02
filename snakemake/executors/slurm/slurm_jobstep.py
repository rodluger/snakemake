import os
import shlex
import sys
import time
import shutil
import subprocess
import tarfile
import tempfile

from snakemake.jobs import Job
from snakemake.shell import shell
from snakemake.logging import logger
from snakemake.deployment.conda import Conda
from snakemake.exceptions import print_exception
from snakemake.exceptions import log_verbose_traceback
from snakemake.exceptions import WorkflowError
from snakemake.executors import ClusterExecutor
from snakemake.utils import makedirs
from snakemake.io import get_wildcard_names, Wildcards



class SlurmJobstepExecutor(ClusterExecutor):
    """
    executes SLURM jobsteps and is *only* instaniated in
    a SLURM job context
    """

    def __init__(
        self,
        workflow,
        dag,
        jobname=None,
        printreason=False,
        quiet=False,
        printshellcmds=False,
        cluster_config=None,
        restart_times=0,
        max_status_checks_per_second=1,
        **kwargs,
    ):
        # overwrite the command to execute a single snakemake job if necessary
        # exec_job = "..."

        super().__init__(
            workflow,
            dag,
            None,
            printreason=printreason,
            quiet=quiet,
            printshellcmds=printshellcmds,
            cluster_config=cluster_config,
            restart_times=restart_times,
            assume_shared_fs=True,
            max_status_checks_per_second=max_status_checks_per_second,
        )

        self.mem_per_node = os.getenv("SLURM_MEM_PER_NODE")
        self.cpus_on_node = os.getenv("SLURM_CPUS_ON_NODE")
        self.jobid = os.getenv("SLURM_JOB_ID")

        self.context = dict(kwargs)
        self.env_modules = self.context.get("env_modules", None)
        
        # if not self.mem_per_node

    def _wait_for_jobs(self):
        pass

    # TODO: place setup code, here, in a first step, then in deployment module
    def environment_setup(self, job):
        pass

    def run(self, job, callback=None, submit_callback=None, error_callback=None):
        jobsteps = dict()
        
        if job.is_group():
            call = self.format_job_exec(job)
            
            #TODO: re-implement, if tested and then with 'resources: group_oversubscribe=True' or similar
            # def get_call(level_job, level_id, aux=""):
            #     # we need this calculation, because of srun's greediness and
            #     # SLURM's limits: it is not able to limit the memory if we divide the job
            #     # per CPU by itself.
            #     mem_per_cpu = max(level_job.resources.mem_mb // level_job.threads, 100)
            #     exec_job = self.format_job_exec(level_job)
            #     return (
            #         f"srun -J {level_id} --jobid {self.jobid}"
            #         f"--mem-per-cpu {mem_per_cpu} -c {level_job.threads}"
            #         f"--exclusive -n 1 {aux} {exec_job}"
            #     )

            # for level in job.toposorted:
            #     for level_id, level_job in enumerate(level[:-1]):
            #         # TODO: spice with srun template
            #         jobsteps[level_job] = subprocess.Popen(
            #             get_call(level_job, level_id), shell=True
            #         )
            #     # this way, we ensure that level jobs depending on the current level get started
            #     jobsteps[level_job] = subprocess.Popen( 
            #         get_call(level_job, level_id + 1, aux="--singleton"), shell=True
            #     )
        # Per default 'srun' is the MPI-starter under SLURM. Hence, users may specify the starter
        # AND specify further flags (e.g. binding of ranks, setting MPI-topoloy, etc.).
        # In an ordinary smp case, binding the (presumably threaded) process, ensures optimal placement
        # regardless of cluster configurations.
        # elif job.resources.get("mpi") and job.shellcmd:
        #     call = f"{cmd}; {job.resources.get('mpi')} {job.shellcmd}"
        # elif job.shellcmd:
        #     call = f"{cmd}; srun --cpu-bind=q --exclusive {job.shellcmd}"
        # elif job.is_script():
        #     call = f"{cmd}; srun --cpu-bind=q --exclusive {job.script}"
        # # in case of the wrapper, the wrapper must take care of the call with regard to SLURM
        # elif job.is_wrapper():
        #     call = f"{job.wrapper}"

        #else:
        if 'mpi' in job.resources.keys():
            # MPI job:
            # No need to prepend `srun`, as this will happen inside of the job's shell command or script (!).
            # The following call invokes snakemake, which in turn takes care of all auxilliary work around the actual command
            # like remote file support, benchmark setup, error handling, etc.
            # AND there can be stuff around the srun call within the job, like any commands which should be executed before.
            call = self.format_job_exec(job)
        else:
            # SMP job, execute snakemake with srun, to ensure proper placing of threaded executables within the c-group
            call = f"srun --cpu-bind=q --exclusive {self.format_job_exec(job)}"            
        
        # this dict is to support the to-implemented feature of oversubscription in "ordinary" group jobs.
        jobsteps[job] = subprocess.Popen(call, shell=True)

        # wait until all steps are finished
        error = False
        for job, proc in jobsteps.items():
            if proc.wait() != 0:
                self.print_job_error(job)
                error = True
        if error:
            error_callback(job)
        else:
            callback(job)

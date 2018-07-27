def savePythonTestArtifacts() {
    archiveArtifacts allowEmptyArchive: true, artifacts: 'reports/**/*,test_root/log/**/*.log,**/nosetests.xml,stdout/*.log,*.log'
    junit '**/nosetests.xml'
}

pipeline {

    agent { label "jenkins-worker" }
    options {
        timestamps()
        timeout(75)
    }
    environment {
        XDIST_CONTAINER_SUBNET = credentials('XDIST_CONTAINER_SUBNET')
        XDIST_CONTAINER_SECURITY_GROUP = credentials('XDIST_CONTAINER_SECURITY_GROUP')
        XDIST_GIT_BRANCH = "${env.ghprbSourceBranch}"
    }
    stages {
        stage('Git checkout'){
            steps {
                sshagent(credentials: ['jenkins-worker'], ignoreMissing: true) {
                    checkout changelog: false, poll: false, scm: [$class: 'GitSCM', branches: [[name: '${sha1}']],
                        doGenerateSubmoduleConfigurations: false, extensions: [], submoduleCfg: [],
                        userRemoteConfigs: [[credentialsId: 'jenkins-worker',
                        refspec: '+refs/heads/*:refs/remotes/origin/* +refs/pull/*:refs/remotes/origin/pr/*',
                        url: 'git@github.com:edx/edx-platform.git']]]
                }
            }
        }
        stage('Run Tests') {
            parallel {
                stage('lms-unit') {
                    environment {
                        XDIST_NUM_TASKS = 10
                        XDIST_CONTAINER_TASK_NAME = "jenkins-worker-task"
                        TEST_SUITE = "lms-unit"
                    }
                    steps {
                        ansiColor('gnome-terminal') {
                            sshagent(credentials: ['jenkins-worker', 'jenkins-worker-pem'], ignoreMissing: true) {
                                sh returnStdout: true, script: 'bash scripts/all-tests.sh'
                                dir('stdout') {
                                    writeFile file: "lms-unit-stdout.log", text: console_output
                                }
                                stash includes: 'reports/**/*coverage*', name: "lms-unit-reports"
                            }
                        }
                    }
                    post {
                        always {
                            script {
                                savePythonTestArtifacts()
                            }
                        }
                    }
                }
            }
        }
    }
}

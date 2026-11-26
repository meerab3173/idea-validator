// Delivery pipeline (after merge to main, and nightly). Runs in a Jenkins
// container that has Docker and the cluster kubeconfig (Jenkins credential
// 'kubeconfig', never in the repo). GitHub cannot reach a laptop, so we poll SCM.
pipeline {
  agent any
  triggers {
    pollSCM('H/2 * * * *')      // check GitHub every ~2 minutes
    cron('H 2 * * *')           // nightly full evaluation
  }
  environment {
    TAG      = "${env.GIT_COMMIT.take(7)}"
    REGISTRY = "${env.REGISTRY ?: 'docker.io/YOUR_DOCKERHUB_USER'}"
    NS       = "idea-validator"
    SERVICES = "gateway profile orchestrator scouts tools kb analyst ideation validators scorer verdict critic agentops"
  }
  options { timestamps(); disableConcurrentBuilds() }
  stages {
    stage('Checkout') { steps { checkout scm } }

    stage('Quick tests') {
      steps { sh './scripts/run_tests.sh' }
    }

    stage('Build') {
      when { not { triggeredBy 'TimerTrigger' } }
      steps { sh './scripts/build_images.sh $TAG' }
    }

    stage('Push') {
      when { not { triggeredBy 'TimerTrigger' } }
      steps {
        withCredentials([usernamePassword(credentialsId: 'registry', usernameVariable: 'REG_USER', passwordVariable: 'REG_PASS')]) {
          sh 'echo "$REG_PASS" | docker login -u "$REG_USER" --password-stdin'
          sh './scripts/push_images.sh $TAG'
        }
      }
    }

    stage('Deploy to test cluster') {
      when { not { triggeredBy 'TimerTrigger' } }
      steps {
        withCredentials([file(credentialsId: 'kubeconfig', variable: 'KUBECONFIG')]) {
          sh './scripts/deploy.sh $TAG'
        }
      }
    }

    stage('Smoke test') {
      when { not { triggeredBy 'TimerTrigger' } }
      steps {
        withCredentials([file(credentialsId: 'kubeconfig', variable: 'KUBECONFIG')]) {
          sh './scripts/smoke_test.sh'
        }
      }
      post {
        failure {
          withCredentials([file(credentialsId: 'kubeconfig', variable: 'KUBECONFIG')]) {
            sh './scripts/rollback.sh'   // bad release -> kubectl rollout undo
          }
        }
      }
    }

    stage('Nightly evaluation') {
      when { triggeredBy 'TimerTrigger' }
      steps {
        withCredentials([file(credentialsId: 'kubeconfig', variable: 'KUBECONFIG')]) {
          sh './scripts/check_eval.sh'
        }
      }
    }
  }
  post {
    failure { echo 'Pipeline failed, nothing promoted' }
    success { echo "Deployed ${env.TAG}" }
  }
}

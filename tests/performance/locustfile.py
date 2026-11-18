from locust import HttpUser, between, task


class BioIntelUser(HttpUser):
    wait_time = between(0.2, 1.2)
    @task(5)
    def readiness(self): self.client.get('/ready', name='/ready')
    @task(3)
    def quality(self): self.client.get('/quality/scorecard', name='/quality/scorecard')
    @task(2)
    def catalog(self): self.client.get('/catalog/datasets', name='/catalog/datasets')

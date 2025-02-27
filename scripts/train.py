from __future__ import print_function
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
from torch.optim.lr_scheduler import StepLR
import optuna
import wandb
from plr_exercise.models.cnn import Net


class Train:
    def __init__(self):
        """
        Initializes the training process for the PyTorch MNIST model.
        Adjust Settings here.
        """

        # Training settings
        parser = argparse.ArgumentParser(description="PyTorch MNIST Example")
        parser.add_argument(
            "--batch-size",
            type=int,
            default=64,
            metavar="N",
            help="input batch size for training (default: 64)",
        )
        parser.add_argument(
            "--test-batch-size",
            type=int,
            default=1000,
            metavar="N",
            help="input batch size for testing (default: 1000)",
        )
        parser.add_argument(
            "--epochs",
            type=int,
            default=2,
            metavar="N",
            help="number of epochs to train (default: 14)",
        )
        parser.add_argument(
            "--lr",
            type=float,
            default=0.0020,
            metavar="LR",
            help="learning rate (default: 1.0)",
        )
        parser.add_argument(
            "--gamma",
            type=float,
            default=0.7,
            metavar="M",
            help="Learning rate step gamma (default: 0.7)",
        )
        parser.add_argument(
            "--no-cuda",
            action="store_true",
            default=False,
            help="disables CUDA training",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="quickly check a single pass",
        )
        parser.add_argument(
            "--seed", type=int, default=1, metavar="S", help="random seed (default: 1)"
        )
        parser.add_argument(
            "--log-interval",
            type=int,
            default=10,
            metavar="N",
            help="how many batches to wait before logging training status",
        )
        parser.add_argument(
            "--save-model",
            action="store_true",
            default=False,
            help="For Saving the current Model",
        )
        self.args = parser.parse_args()
        use_cuda = not self.args.no_cuda and torch.cuda.is_available()

        torch.manual_seed(self.args.seed)

        if use_cuda:
            self.device = torch.device("cuda")
        else:
            self.device = torch.device("cpu")

        # wandb.login()
        # Initialize wandb
        wandb.init(
            # Set the project where this run will be logged
            project="plr_exercies",
            # Track hyperparameters and run metadata
            config={
                "learning_rate": self.args.lr,
                "epochs": self.args.epochs,
            },
            save_code=True,
        )

        train_kwargs = {"batch_size": self.args.batch_size}
        test_kwargs = {"batch_size": self.args.test_batch_size}
        if use_cuda:
            cuda_kwargs = {"num_workers": 1, "pin_memory": True, "shuffle": True}
            train_kwargs.update(cuda_kwargs)
            test_kwargs.update(cuda_kwargs)

        # Configure and import Data
        transform = transforms.Compose(
            [transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))]
        )
        dataset1 = datasets.MNIST(
            "../data", train=True, download=True, transform=transform
        )
        dataset2 = datasets.MNIST("../data", train=False, transform=transform)

        self.train_loader = torch.utils.data.DataLoader(dataset1, **train_kwargs)
        self.test_loader = torch.utils.data.DataLoader(dataset2, **test_kwargs)
        self.model = Net().to(self.device)
        self.optimizer = optim.Adam(self.model.parameters(), lr=self.args.lr)
        self.scheduler = StepLR(self.optimizer, step_size=1, gamma=self.args.gamma)

    def train(self, epoch):
        """
        Trains the model on the training data for specified epochs.

        Args:
            epoch (int): The current epoch number. Determined by the objective function.

        Returns:
            None
        """
        self.model.train()
        for batch_idx, (data, target) in enumerate(self.train_loader):
            data, target = data.to(self.device), target.to(self.device)
            self.optimizer.zero_grad()
            output = self.model(data)
            loss = F.nll_loss(output, target)
            loss.backward()
            self.optimizer.step()
            if batch_idx % self.args.log_interval == 0:
                wandb.log({"training_loss": loss})
                print(
                    "Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}".format(
                        epoch,
                        batch_idx * len(data),
                        len(self.train_loader.dataset),
                        100.0 * batch_idx / len(self.train_loader),
                        loss.item(),
                    )
                )
                if self.args.dry_run:
                    break

    def test(self) -> float:
        """
        Evaluate the performance of the model on the test dataset.

        Returns:
            Accuracy (float): The accuracy of the model on the test dataset.
        """
        self.model.eval()
        test_loss = 0
        correct = 0

        with torch.no_grad():
            for data, target in self.test_loader:

                data, target = data.to(self.device), target.to(self.device)
                output = self.model(data)
                test_loss += F.nll_loss(
                    output, target, reduction="sum"
                ).item()  # sum up batch loss
                pred = output.argmax(
                    dim=1, keepdim=True
                )  # get the index of the max log-probability
                correct += pred.eq(target.view_as(pred)).sum().item()

        test_loss /= len(self.test_loader.dataset)
        wandb.log({"test_loss": test_loss})

        print(
            "\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n".format(
                test_loss,
                correct,
                len(self.test_loader.dataset),
                100.0 * correct / len(self.test_loader.dataset),
            )
        )

        return correct / len(self.test_loader.dataset)


def objective(trial):
    """
    Objective function for the Optuna hyperparameter optimization.

    Args:
        trial (optuna.Trial): The current trial for the hyperparameter optimization.

    Returns:
        accuracy (float): The accuracy of the model on the test dataset.
    """
    t = Train()

    # Get the hyperparameters for the current trial and update parser
    lr = trial.suggest_float("lr", 1e-5, 1e-1, log=True)
    epochs = trial.suggest_int("epochs", 1, 1)
    optimizer = optim.Adam(t.model.parameters(), lr=lr)
    scheduler = StepLR(optimizer, step_size=1, gamma=t.args.gamma)
    for epoch in range(epochs):
        t.train(epoch)
        accuracy = t.test()
        scheduler.step()

    if t.args.save_model:
        torch.save(t.model.state_dict(), "mnist_cnn.pt")

    return accuracy


def main():
    """
    Main function for training a PyTorch MNIST model.
    Creating an Optuna for automatic hyperparameter tuning.
    Logs with WandDB

    """
    # send model to objective function for hyperparameter optimization
    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=5, timeout=600)

    trial = study.best_trial
    print("Best trial: ", trial.params)


if __name__ == "__main__":
    main()

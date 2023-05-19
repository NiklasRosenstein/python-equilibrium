# equilibrium

> __Equilibrium__ _(noun)_: A state in which opposing forces or influences are balanced, resulting in a stable system
> that does not undergo significant changes. In a broader sense, equilibrium can refer to a state of mental or emotional
> balance, as well as the balance of forces in physical or chemical systems.

Equilibrium is a Python framework inspired by various other open-source tools for implementing control loops
(Kubernetes) and rules-engines (Pants build system).

## Overview: Resource management & control loops

Equilibrium is a framework for implementing control loops. A control loop is a system that continuously monitors
the state of a system and takes action to bring the system into a desired state. Equilibrium is designed to be
extensible and flexible, allowing you to implement control loops that are tailored to your specific use case.

Check out the [examples/local_file/](examples/local_file/) directory for a simple example of a control loop that
monitors a local file and takes action when the file is modified.

__Difference to Kubernetes resources__

* Equilibrium does not currently support any key other than `spec` next to `apiVersion`, `kind`, and `metadata` in
  a resource definition. This means Equilibrium cannot be used to deserialize actual Kubernetes `Secret` of `Config`
  resources.

## Overview: Rules engine

Equilibrium is also a framework for implementing rules engines. A rules engine is a system derives a sequence of rules
to execute to reach a desired and goal based on a given set of inputs, ensuring that rules are never exexcuted multiple
times with the same inputs.

Check out the [examples/codegen/](examples/codegen/) directory for a simple example of a rules engine that generates
Terraform code based on a set of Kubernetes-like resources. This example combines the resource management API with
the rules engine API.

## Installation

Equilibrium is available on PyPI:

```bash
pip install python-equilibrium
```

It requires at least Python 3.10.

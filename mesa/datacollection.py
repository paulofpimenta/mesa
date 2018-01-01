# -*- coding: utf-8 -*-
"""
Mesa Data Collection Module
===========================

DataCollector is meant to provide a simple, standard way to collect data
generated by a Mesa model. It collects three types of data: model-level data,
agent-level data, and tables.

A DataCollector is instantiated with two dictionaries of reporter names and
associated variable names or functions for each, one for model-level data and
one for agent-level data; a third dictionary provides table names and columns.
Variable names are converted into functions which retrieve attributes of that
name.

When the collect() method is called, each model-level function is called, with
the model as the argument, and the results associated with the relevant
variable. Then the agent-level functions are called on each agent in the model
scheduler.

Additionally, other objects can write directly to tables by passing in an
appropriate dictionary object for a table row.

The DataCollector then stores the data it collects in dictionaries:
    * model_vars maps each reporter to a list of its values
    * agent_vars maps each reporter to a list of lists, where each nested list
      stores (agent_id, value) pairs.
    * tables maps each table to a dictionary, with each column as a key with a
      list as its value.

Finally, DataCollector can create a pandas DataFrame from each collection.

The default DataCollector here makes several assumptions:
    * The model has a schedule object called 'schedule'
    * The schedule has an agent list called agents
    * For collecting agent-level variables, agents must have a unique_id

"""
from collections import defaultdict
import pandas as pd


class DataCollector:
    """ Class for collecting data generated by a Mesa model.

    A DataCollector is instantiated with dictionaries of names of model- and
    agent-level variables to collect, associated with attribute names or 
    functions which actually collect them. When the collect(...) method is
    called, it collects these attributes and executes these functions one by
    one and stores the results.

    """

    model = None

    def __init__(self, model_reporters=None, agent_reporters=None, tables=None):
        """ Instantiate a DataCollector with lists of model and agent reporters.

        Both model_reporters and agent_reporters accept a dictionary mapping a
        variable name to either an attribute name, or a method.
        For example, if there was only one model-level reporter for number of
        agents, it might look like:
            {"agent_count": lambda m: m.schedule.get_agent_count() }
        If there was only one agent-level reporter (e.g. the agent's energy),
        it might look like this:
            {"energy": lambda a: a.energy}
        or like this:
            {"energy": "energy"}

        The tables arg accepts a dictionary mapping names of tables to lists of
        columns. For example, if we want to allow agents to write their age
        when they are destroyed (to keep track of lifespans), it might look
        like:
            {"Lifespan": ["unique_id", "age"]}

        Args:
            model_reporters: Dictionary of reporter names and attributes/funcs
            agent_reporters: Dictionary of reporter names and attributes/funcs.
            tables: Dictionary of table names to lists of column names.

        """
        self.model_reporters = {}
        self.agent_reporters = {}

        self.model_vars = {}
        self.agent_vars = {}
        self.tables = {}

        if model_reporters is not None:
            for name, reporter in model_reporters.items():
                self._new_model_reporter(name, reporter)

        if agent_reporters is not None:
            for name, reporter in agent_reporters.items():
                self._new_agent_reporter(name, reporter)

        if tables is not None:
            for name, columns in tables.items():
                self._new_table(name, columns)

    def _new_model_reporter(self, name, reporter):
        """ Add a new model-level reporter to collect.

        Args:
            name: Name of the model-level variable to collect.
            reporter: Attribute string, or function object that returns the
                      variable when given a model instance.
        """
        if type(reporter) is str:
            reporter = self._make_attribute_collector(reporter)
        self.model_reporters[name] = reporter
        self.model_vars[name] = []

    def _new_agent_reporter(self, name, reporter):
        """ Add a new agent-level reporter to collect.

        Args:
            name: Name of the agent-level variable to collect.
            reporter: Attribute string, or function object that returns the
                      variable when given a model instance.

        """
        if type(reporter) is str:
            reporter = self._make_attribute_collector(reporter)
        self.agent_reporters[name] = reporter
        self.agent_vars[name] = []

    def _new_table(self, table_name, table_columns):
        """ Add a new table that objects can write to.

        Args:
            table_name: Name of the new table.
            table_columns: List of columns to add to the table.

        """
        new_table = {column: [] for column in table_columns}
        self.tables[table_name] = new_table

    def collect(self, model):
        """ Collect all the data for the given model object. """
        if self.model_reporters:
            for var, reporter in self.model_reporters.items():
                self.model_vars[var].append(reporter(model))

        if self.agent_reporters:
            for var, reporter in self.agent_reporters.items():
                agent_records = []
                for agent in model.schedule.agents:
                    agent_records.append((agent.unique_id, reporter(agent)))
                self.agent_vars[var].append(agent_records)

    def add_table_row(self, table_name, row, ignore_missing=False):
        """ Add a row dictionary to a specific table.

        Args:
            table_name: Name of the table to append a row to.
            row: A dictionary of the form {column_name: value...}
            ignore_missing: If True, fill any missing columns with Nones;
                            if False, throw an error if any columns are missing

        """
        if table_name not in self.tables:
            raise Exception("Table does not exist.")

        for column in self.tables[table_name]:
            if column in row:
                self.tables[table_name][column].append(row[column])
            elif ignore_missing:
                self.tables[table_name][column].append(None)
            else:
                raise Exception("Could not insert row with missing column")

    @staticmethod
    def _make_attribute_collector(attr):
        '''
        Create a function which collects the value of a named attribute
        '''

        def attr_collector(obj):
            return getattr(obj, attr)

        return attr_collector

    def get_model_vars_dataframe(self):
        """ Create a pandas DataFrame from the model variables.

        The DataFrame has one column for each model variable, and the index is
        (implicitly) the model tick.

        """
        return pd.DataFrame(self.model_vars)

    def get_agent_vars_dataframe(self):
        """ Create a pandas DataFrame from the agent variables.

        The DataFrame has one column for each variable, with two additional
        columns for tick and agent_id.

        """
        data = defaultdict(dict)
        for var, records in self.agent_vars.items():
            for step, entries in enumerate(records):
                for entry in entries:
                    agent_id = entry[0]
                    val = entry[1]
                    data[(step, agent_id)][var] = val
        df = pd.DataFrame.from_dict(data, orient="index")
        df.index.names = ["Step", "AgentID"]
        return df

    def get_table_dataframe(self, table_name):
        """ Create a pandas DataFrame from a particular table.

        Args:
            table_name: The name of the table to convert.

        """
        if table_name not in self.tables:
            raise Exception("No such table.")
        return pd.DataFrame(self.tables[table_name])

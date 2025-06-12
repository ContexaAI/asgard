#!/bin/bash


mkdir -p .conf
mkdir -p .env

# Copy files from .env.example/*  to .env/
cp -r env.example/* .env/

# Copy files from .conf.example/*  to .conf/
cp -r conf.example/* .conf/

# Set permissions for .env files
chmod 600 .env/*

# Set permissions for .conf files
chmod 600 .conf/*


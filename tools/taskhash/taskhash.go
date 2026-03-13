package main

import (
	"crypto/md5"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type Config struct {
	Includes []string `json:"includes"`
	Excludes []string `json:"excludes"`
	Store    string   `json:"store"`
}

func main() {
	task := flag.String("task", "default", "Task name to check/update")
	check := flag.Bool("check", false, "Check if signature matches")
	update := flag.Bool("update", false, "Update signature to current")
	force := flag.Bool("force", false, "Force mismatch during check")
	configPath := flag.String("config", "taskhash.json", "Path to config file")
	initFlag := flag.Bool("init", false, "Initialize a taskhash.json with sensible defaults")

	flag.Parse()

	if *initFlag {
		err := initializeConfig(*configPath)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error initializing config: %v\n", err)
			os.Exit(2)
		}
		fmt.Printf("Initialized %s\n", *configPath)
		os.Exit(0)
	}

	config, err := loadConfig(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading config: %v\n", err)
		os.Exit(2)
	}

	currentSig, err := calculateSignature(config)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error calculating signature: %v\n", err)
		os.Exit(2)
	}

	signatures, err := loadSignatures(config.Store)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading signatures: %v\n", err)
		os.Exit(2)
	}

	if *check {
		if *force {
			os.Exit(1)
		}
		if signatures[*task] == currentSig {
			os.Exit(0)
		} else {
			os.Exit(1)
		}
	}

	if *update {
		signatures[*task] = currentSig
		err = saveSignatures(config.Store, signatures)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error saving signatures: %v\n", err)
			os.Exit(2)
		}
		fmt.Printf("Code signature updated for task '%s': %s\n", *task, currentSig)
	} else if !*check {
		fmt.Println(currentSig)
	}
}

func initializeConfig(path string) error {
	// 1. Detect common folders
	commonFolders := []string{"src", "lib", "app", "tests", "scripts", "Makefile", "pyproject.toml", "package.json", "go.mod"}
	detected := []string{}
	for _, folder := range commonFolders {
		if _, err := os.Stat(folder); err == nil {
			detected = append(detected, folder)
		}
	}

	// 2. Fallback to 'src' if nothing found
	if len(detected) == 0 {
		detected = []string{"src"}
	}

	config := &Config{
		Includes: detected,
		Excludes: []string{
			".git", 
			"__pycache__", 
			"node_modules", 
			"vendor", 
			".code_signatures.json", 
			"taskhash",
			"taskhash.exe",
		},
		Store: ".code_signatures.json",
	}

	data, err := json.MarshalIndent(config, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

func loadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			// Sensible default config if no file exists
			return &Config{
				Includes: []string{"src", "lib", "app", "tests", "scripts", "Makefile", "pyproject.toml", "package.json", "go.mod"},
				Excludes: []string{
					".git", 
					"__pycache__", 
					"node_modules", 
					"vendor", 
					".code_signatures.json", 
					"taskhash",
					"taskhash.exe",
					"docs",
				},
				Store: ".code_signatures.json",
			}, nil
		}
		return nil, err
	}
	var config Config
	err = json.Unmarshal(data, &config)
	if err != nil {
		return nil, err
	}
	if config.Store == "" {
		config.Store = ".code_signatures.json"
	}
	return &config, nil
}

func calculateSignature(config *Config) (string, error) {
	hasher := md5.New()
	var files []string

	for _, include := range config.Includes {
		err := filepath.Walk(include, func(path string, info os.FileInfo, err error) error {
			if err != nil {
				return nil // Skip errors
			}
			if info.IsDir() {
				return nil
			}

			// Check excludes
			rel, _ := filepath.Rel(".", path)
			for _, ex := range config.Excludes {
				if strings.Contains(rel, ex) {
					return nil
				}
			}

			files = append(files, path)
			return nil
		})
		if err != nil {
			return "", err
		}
	}

	sort.Strings(files)

	for _, f := range files {
		file, err := os.Open(f)
		if err != nil {
			continue
		}
		if _, err := io.Copy(hasher, file); err != nil {
			file.Close()
			return "", err
		}
		file.Close()
	}

	return hex.EncodeToString(hasher.Sum(nil)), nil
}

func loadSignatures(path string) (map[string]string, error) {
	sigs := make(map[string]string)
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return sigs, nil
		}
		return nil, err
	}
	err = json.Unmarshal(data, &sigs)
	return sigs, err
}

func saveSignatures(path string, sigs map[string]string) error {
	data, err := json.MarshalIndent(sigs, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

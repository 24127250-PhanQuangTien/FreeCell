from gui import FreeCellGUI, tk


if __name__ == "__main__":
    root = tk.Tk()
    app  = FreeCellGUI(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nĐã tắt game.")
import gradio as gr
import pyedflib
import plotly.graph_objs as go
import numpy as np
import json


def time_to_seconds(time_str):
    """Преобразует строку времени в формате HH:MM:SS в секунды."""
    h, m, s = map(int, time_str.split(':'))
    return h * 3600 + m * 60 + s


def seconds_to_time(seconds):
    """Преобразует секунды в строку времени в формате HH:MM:SS."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{int(h):02}:{int(m):02}:{int(s):02}"


def load_edf_with_annotations(edf_file, annotations_file):
    try:
        # Чтение EDF файла
        edf = pyedflib.EdfReader(edf_file.name)
        n_signals = edf.signals_in_file
        signal_labels = edf.getSignalLabels()

        # Получение данных всех сигналов и частоты дискретизации
        data = {}
        sample_rate = {}
        for i in range(n_signals):
            data[signal_labels[i]] = edf.readSignal(i)
            sample_rate[signal_labels[i]] = edf.getSampleFrequency(i)

        edf.close()

        # Проверка загрузки сигналов
        if not signal_labels:
            print("No signals found in the EDF file.")
        else:
            print(f"Signals loaded: {signal_labels}")

        # Чтение аннотаций из текстового файла
        annotations = []
        with open(annotations_file.name, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) != 3:
                    print(f"Skipping invalid line: {line}")
                    continue
                try:
                    onset = time_to_seconds(parts[1])
                    description = parts[2]
                    annotations.append({'time': onset, 'description': description})
                except ValueError as e:
                    print(f"Skipping line with invalid values: {line} ({e})")

        # Создание интервалов для аннотаций
        intervals = []
        for i in range(0, len(annotations) - 1, 2):
            if i + 1 < len(annotations):
                start_annotation = annotations[i]
                end_annotation = annotations[i + 1]
                if (start_annotation['description'][:-1] == end_annotation['description'][:-1] and
                        start_annotation['description'][-1] == '1' and end_annotation['description'][-1] == '2'):
                    intervals.append({
                        'start': start_annotation['time'],
                        'end': end_annotation['time'],
                        'description': start_annotation['description'][:-1]  # swd, is, ds
                    })

        print(f"Intervals created: {intervals}")
        interval_choices = [
            f"{i + 1}: {seconds_to_time(interval['start'])} - {seconds_to_time(interval['end'])} ({interval['description']})"
            for i, interval in enumerate(intervals)]
        return data, sample_rate, intervals, gr.update(choices=signal_labels), gr.update(
            choices=interval_choices), interval_choices, ""
    except Exception as e:
        print(f"Error loading EDF or annotations: {str(e)}")
        return {}, {}, [], gr.update(choices=[]), gr.update(choices=[]), [], str(e)


def plot_signal(edf_data, sample_rate, intervals, signal_label, markup_intervals):
    if not edf_data or not signal_label:
        return None

    # Получение данных для выбранного сигнала и частоты дискретизации
    signal_data = edf_data.get(signal_label, [])
    fs = sample_rate.get(signal_label, 1)  # Частота дискретизации (по умолчанию 1 для безопасности)

    # Создание временной шкалы
    time_axis = np.arange(len(signal_data)) / fs

    # Создание интерактивного графика с помощью plotly
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=time_axis, y=signal_data, mode='lines', name=signal_label))

    # Определение более насыщенных цветов для различных фаз
    phase_colors = {
        'swd': 'rgba(255, 0, 0, 0.7)',  # Более насыщенный красный для SWD
        'is': 'rgba(0, 255, 0, 0.7)',  # Более насыщенный зеленый для IS
        'ds': 'rgba(0, 0, 255, 0.7)'  # Более насыщенный синий для DS
    }

    # Добавление цветных полос для аннотаций
    for interval in intervals + markup_intervals:
        description_lower = interval['description'].lower()
        color = phase_colors.get(description_lower, 'rgba(0, 0, 0, 0)')  # Черный цвет по умолчанию

        fig.add_shape(type='rect',
                      x0=interval['start'], x1=interval['end'],
                      y0=min(signal_data), y1=max(signal_data),
                      fillcolor=color, opacity=0.7, line_width=0)

    fig.update_layout(
        title=f"Сигнал: {signal_label}",
        xaxis_title="Время (секунды)",
        yaxis_title="Амплитуда",
        showlegend=True
    )

    return fig


def add_markup(start_time, end_time, label, markup_intervals):
    """Добавляет пользовательскую разметку."""
    markup_intervals.append({'start': start_time, 'end': end_time, 'description': label})
    return markup_intervals


def edit_markup(selected_interval, start_time, end_time, label, existing_intervals, markup_intervals):
    """Редактирует существующую разметку."""
    all_intervals = existing_intervals + markup_intervals
    index = int(selected_interval.split(":")[0]) - 1
    interval = all_intervals[index]
    interval['start'] = start_time
    interval['end'] = end_time
    interval['description'] = label
    interval_choices = [
        f"{i + 1}: {seconds_to_time(interval['start'])} - {seconds_to_time(interval['end'])} ({interval['description']})"
        for i, interval in enumerate(all_intervals)]
    return all_intervals, interval_choices


def delete_markup(selected_interval, existing_intervals, markup_intervals):
    """Удаляет существующую разметку."""
    all_intervals = existing_intervals + markup_intervals
    index = int(selected_interval.split(":")[0]) - 1
    del all_intervals[index]
    interval_choices = [
        f"{i + 1}: {seconds_to_time(interval['start'])} - {seconds_to_time(interval['end'])} ({interval['description']})"
        for i, interval in enumerate(all_intervals)]
    return all_intervals, interval_choices


def save_markup_to_file(markup_intervals, existing_intervals, filename_json, filename_txt):
    """Сохраняет разметку в JSON и TXT файлы."""
    all_intervals = existing_intervals + markup_intervals

    # Сохранение в JSON файл
    with open(filename_json, 'w') as f:
        json.dump(all_intervals, f, ensure_ascii=False, indent=4)

    # Сохранение в TXT файл
    with open(filename_txt, 'w') as f:
        for i, interval in enumerate(all_intervals):
            start_time = seconds_to_time(interval['start'])
            end_time = seconds_to_time(interval['end'])
            f.write(f"{i+1}  {start_time}  {interval['description']}1\n")
            f.write(f"{i+1}  {end_time}    {interval['description']}2\n")

    return f"Markup saved to {filename_json} and {filename_txt}"


# Создание интерфейса Gradio
with gr.Blocks() as demo:
    # Блок загрузки файлов
    gr.Markdown("## Загрузка файлов")
    file_input = gr.File(label="Загрузите EDF файл")
    annotations_input = gr.File(label="Загрузите файл с аннотациями (.txt)")
    load_button = gr.Button("Загрузить файл")

    # Поля для вывода ошибок
    error_output = gr.Textbox(label="Ошибка", visible=False)

    # Дропдаун для выбора сигнала
    signal_dropdown = gr.Dropdown(choices=[], label="Выберите сигнал", allow_custom_value=False)

    # График для визуализации
    plot_output = gr.Plot()

    # Блок для добавления разметки
    gr.Markdown("## Добавление разметки")
    start_time_input = gr.Number(label="Start Time (seconds)")
    end_time_input = gr.Number(label="End Time (seconds)")
    label_input = gr.Dropdown(choices=["swd", "is", "ds"], label="Label")
    add_markup_button = gr.Button("Add Markup")
# Состояния для хранения данных EDF, частоты дискретизации и аннотаций
    edf_data_output = gr.State()
    sample_rate_output = gr.State()
    annotations_output = gr.State([])
    interval_choices_output = gr.State([])

    # Блок для редактирования и удаления разметки
    gr.Markdown("## Редактирование и удаление разметки")
    selected_interval = gr.Dropdown(choices=[], label="Выберите интервал для редактирования")
    edit_start_time_input = gr.Number(label="Edit Start Time (seconds)")
    edit_end_time_input = gr.Number(label="Edit End Time (seconds)")
    edit_label_input = gr.Dropdown(choices=["swd", "is", "ds"], label="Edit Label")
    edit_markup_button = gr.Button("Edit Markup")
    delete_markup_button = gr.Button("Delete Markup")

    # Кнопка для сохранения разметки
    gr.Markdown("## Сохранение разметки")
    save_markup_button = gr.Button("Save Markup")

    # Определение логики обработки при нажатии на кнопки
    load_button.click(
        fn=load_edf_with_annotations,
        inputs=[file_input, annotations_input],
        outputs=[edf_data_output, sample_rate_output, annotations_output, signal_dropdown, selected_interval, error_output]
    )

    add_markup_button.click(
        fn=add_markup,
        inputs=[start_time_input, end_time_input, label_input, annotations_output],
        outputs=annotations_output
    ).then(
        fn=lambda existing_intervals, markup_intervals: (
            existing_intervals + markup_intervals,
            [f"{i+1}: {seconds_to_time(interval['start'])} - {seconds_to_time(interval['end'])} ({interval['description']})" for i, interval in enumerate(existing_intervals + markup_intervals)]
        ),
        inputs=[annotations_output, annotations_output],
        outputs=[annotations_output, interval_choices_output]
    ).then(
        fn=plot_signal,
        inputs=[edf_data_output, sample_rate_output, annotations_output, signal_dropdown, annotations_output],
        outputs=plot_output
    )

    edit_markup_button.click(
        fn=edit_markup,
        inputs=[selected_interval, edit_start_time_input, edit_end_time_input, edit_label_input, annotations_output, annotations_output],
        outputs=[annotations_output, interval_choices_output]
    ).then(
        fn=plot_signal,
        inputs=[edf_data_output, sample_rate_output, annotations_output, signal_dropdown, annotations_output],
        outputs=plot_output
    )

    delete_markup_button.click(
        fn=delete_markup,
        inputs=[selected_interval, annotations_output, annotations_output],
        outputs=[annotations_output, interval_choices_output]
    ).then(
        fn=plot_signal,
        inputs=[edf_data_output, sample_rate_output, annotations_output, signal_dropdown, annotations_output],
        outputs=plot_output
    )

    save_markup_button.click(
        fn=save_markup_to_file,
        inputs=[annotations_output, annotations_output, gr.Textbox(label="Filename JSON", value="markup.json"), gr.Textbox(label="Filename TXT", value="markup.txt")],
        outputs=gr.Textbox(label="Save Status")
    )

    signal_dropdown.change(
        fn=plot_signal,
        inputs=[edf_data_output, sample_rate_output, annotations_output, signal_dropdown, annotations_output],
        outputs=plot_output
    )

    # Размещение компонентов друг под другом
    file_input
    annotations_input
    load_button
    error_output
    signal_dropdown
    plot_output
    start_time_input
    end_time_input
    label_input
    add_markup_button
    selected_interval
    edit_start_time_input
    edit_end_time_input
    edit_label_input
    edit_markup_button
    delete_markup_button
    save_markup_button

# Запуск приложения
demo.launch(share=True)
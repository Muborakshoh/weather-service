import React, { useState } from 'react';
import { Box, Button, TextField, Select, MenuItem } from '@mui/material';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';

const Weather = () => {
  const [city, setCity] = useState('');
  const [weather, setWeather] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(5);
  const [displayMode, setDisplayMode] = useState('chart');
  const [language, setLanguage] = useState('ru');

  const fetchWeather = async () => {
    try {
      console.log(`Fetching weather for ${city} with lang=${language}`);
      const response = await axios.get(`/forecast/${city}`, {
        params: { lang: language },
      });
      console.log('Response:', response.data);
      setWeather(response.data);
      setError(null);
      fetchHistory();
    } catch (err) {
      console.error('Error:', err);
      if (err.response) {
        // Ошибка от сервера (например, 404 или 500)
        setError(
          language === 'ru'
            ? err.response.status === 404
              ? 'Город не найден'
              : 'Ошибка сервера'
            : err.response.status === 404
            ? 'City not found'
            : 'Server error'
        );
      } else {
        // Ошибка сети или другая
        setError(language === 'ru' ? 'Ошибка сети' : 'Network error');
      }
      setWeather(null);
    }
  };

  const fetchHistory = async () => {
    try {
      const response = await axios.get('/weather_history', {
        params: { limit: 14 },
      });
      console.log('History response:', response.data);
      setHistory(response.data.history);
    } catch (err) {
      console.error('History fetch error:', err.message);
      setHistory([]);
    }
  };

  // Функция translateDescription больше не нужна, так как бэкенд возвращает описание на нужном языке
  const translateDescription = (description) => description;

  const renderChartView = () => (
    <Box sx={{ marginTop: 3 }}>
      <h2>{weather.city}</h2>
      <LineChart width={600} height={300} data={weather.forecast.slice(0, days)}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="date" />
        <YAxis />
        <Tooltip />
        <Legend />
        <Line type="monotone" dataKey="temperature" stroke="#8884d8" name={language === 'ru' ? 'Температура' : 'Temperature'} />
      </LineChart>
      {weather.forecast.slice(0, days).map((day, index) => {
        const iconUrl = `http://openweathermap.org/img/wn/${day.icon}@2x.png`;
        return (
          <Box key={index} sx={{ margin: 2, border: '1px solid #ccc', padding: 2 }}>
            <p>{language === 'ru' ? 'Дата' : 'Date'}: {day.date}</p>
            <img src={iconUrl} alt="Weather icon" />
            <p>{language === 'ru' ? 'Температура' : 'Temperature'}: {day.temperature}°C</p>
            <p>{language === 'ru' ? 'Описание' : 'Description'}: {translateDescription(day.description)}</p>
          </Box>
        );
      })}
      <p>{weather.fromCache ? 'From cache' : 'From OpenWeatherMap'}</p>
    </Box>
  );

  const renderListView = () => (
    <Box sx={{ marginTop: 3 }}>
      <h2>{weather.city}</h2>
      {weather.forecast.map((day, index) => {
        const iconUrl = `http://openweathermap.org/img/wn/${day.icon}@2x.png`;
        return (
          <Box key={index} sx={{ margin: 2, border: '1px solid #ccc', padding: 2 }}>
            <p>{language === 'ru' ? 'Дата' : 'Date'}: {day.date}</p>
            <img src={iconUrl} alt="Weather icon" />
            <p>{language === 'ru' ? 'Температура' : 'Temperature'}: {day.temperature}°C</p>
            <p>{language === 'ru' ? 'Описание' : 'Description'}: {translateDescription(day.description)}</p>
          </Box>
        );
      })}
      <p>{weather.fromCache ? 'From cache' : 'From OpenWeatherMap'}</p>
    </Box>
  );

  const renderHistory = () => {
    // Группируем записи по 7 (неделя)
    const rows = [];
    for (let i = 0; i < history.length; i += 7) {
      rows.push(history.slice(i, i + 7));
    }

    return (
      <Box sx={{ marginTop: 3 }}>
        <h2>{language === 'ru' ? 'История запросов' : 'Request History'}</h2>
        {history.length > 0 ? (
          <Box>
            {rows.map((row, rowIndex) => (
              <Box
                key={rowIndex}
                sx={{
                  display: 'flex',
                  justifyContent: 'center',
                  gap: 2,
                  marginBottom: 2,
                  flexWrap: 'wrap', // Для адаптивности
                }}
              >
                {row.map((entry, index) => {
                  const iconUrl = `http://openweathermap.org/img/wn/${entry.icon}@2x.png`;
                  return (
                    <Box
                      key={index}
                      sx={{
                        width: 120,
                        height: 150,
                        border: '1px solid #ccc',
                        borderRadius: 2,
                        padding: 1,
                        textAlign: 'center',
                        backgroundColor: '#f0f0f0',
                        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                      }}
                    >
                      <Box>
                        <p style={{ fontSize: '14px', margin: '2px 0', fontWeight: 'bold' }}>{entry.city}</p>
                        <p style={{ fontSize: '12px', margin: '2px 0' }}>
                          {new Date(entry.forecast_date).toLocaleDateString()}
                        </p>
                        <img src={iconUrl} alt="Weather icon" style={{ width: 50, height: 50 }} />
                        <p style={{ fontSize: '12px', margin: '2px 0' }}>
                          {entry.avg_temperature.toFixed(1)}°C
                        </p>
                      </Box>
                      <p style={{ fontSize: '12px', margin: '2px 0', color: '#555' }}>
                        {translateDescription(entry.description)}
                      </p>
                    </Box>
                  );
                })}
                {/* Заполняем пустые ячейки, если в ряду меньше 7 записей */}
                {Array.from({ length: 7 - row.length }).map((_, index) => (
                  <Box
                    key={`empty-${index}`}
                    sx={{
                      width: 120,
                      height: 150,
                      border: '1px solid transparent',
                    }}
                  />
                ))}
              </Box>
            ))}
          </Box>
        ) : (
          <p>{language === 'ru' ? 'История пока пуста' : 'History is empty'}</p>
        )}
      </Box>
    );
  };

  return (
    <Box sx={{ textAlign: 'center', marginTop: 5 }}>
      <TextField
        label={language === 'ru' ? 'Введите название города' : 'Enter city name'}
        variant="outlined"
        value={city}
        onChange={(e) => setCity(e.target.value)}
        placeholder={language === 'ru' ? 'Например, Москва или London' : 'E.g., Moscow or London'}
        sx={{ marginRight: 2 }}
      />
      <Select
        value={days}
        onChange={(e) => setDays(e.target.value)}
        sx={{ marginRight: 2 }}
      >
        <MenuItem value={1}>{language === 'ru' ? '1 день' : '1 day'}</MenuItem>
        <MenuItem value={3}>{language === 'ru' ? '3 дня' : '3 days'}</MenuItem>
        <MenuItem value={5}>{language === 'ru' ? '5 дней' : '5 days'}</MenuItem>
        <MenuItem value={7}>{language === 'ru' ? '7 дней' : '7 days'}</MenuItem>
        <MenuItem value={15}>{language === 'ru' ? '15 дней' : '15 days'}</MenuItem>
        <MenuItem value={30}>{language === 'ru' ? '30 дней' : '30 days'}</MenuItem>
      </Select>
      <Button variant="contained" color="primary" onClick={fetchWeather}>
        {language === 'ru' ? 'Узнать погоду' : 'Get Weather'}
      </Button>
      <Button
        variant="outlined"
        onClick={() => setLanguage(language === 'ru' ? 'en' : 'ru')}
        sx={{ marginLeft: 2 }}
      >
        {language === 'ru' ? 'English' : 'Русский'}
      </Button>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      {weather && (
        <>
          {displayMode === 'chart' ? renderChartView() : renderListView()}
          <Button
            variant="outlined"
            onClick={() => setDisplayMode(displayMode === 'chart' ? 'list' : 'chart')}
            sx={{ marginTop: 2 }}
          >
            {displayMode === 'chart'
              ? language === 'ru' ? 'Показать список' : 'Show List'
              : language === 'ru' ? 'Показать график' : 'Show Chart'}
          </Button>
        </>
      )}

      {renderHistory()}
    </Box>
  );
};

export default Weather;